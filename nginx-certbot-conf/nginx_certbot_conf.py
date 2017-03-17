#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import logging
import multiprocessing
import os
import signal
import subprocess
import time

import docker
import jinja2

_logger = logging.getLogger(__name__)

CERTBOT_CERT_PATH = "/etc/letsencrypt/live"
NGINX_VHOSTS_CONF_PATH = "/srv/nginx-vhosts-conf.d"

LETSENCRYPT_EMAIL = os.environ.get('LETSENCRYPT_EMAIL', 'info@example.com')


class ContainerNotFoundException(Exception):
    pass


class WorkQueue(object):
    def __init__(self, function=None, delay=10):
        self.event = multiprocessing.Event()
        self.delay = delay
        self.function = function
        self.process = multiprocessing.Process(
            target=self.run,
        )
        self.process.daemon = True

    def run(self):
        while True:
            _logger.debug('waiting for signal')
            self.event.wait()
            _logger.debug('recieved signal, waiting')
            time.sleep(self.delay)
            _logger.debug('running func')
            self.function()
            self.event.clear()

    def signal(self):
        _logger.debug('Send signal')
        self.event.set()

    def start(self):
        _logger.debug('Starting up')
        self.process.start()


class NginxCertbotConfigurator(object):
    def __init__(self):
        self.docker_client = docker.from_env()

        self.template_vhosts_conf = jinja2.Environment(
            loader=jinja2.FileSystemLoader('/')
        ).get_template('odoo-vhost.conf.j2')

        self.nginx_queue = WorkQueue(
            function=self.renew_nginx_config,
            delay=10
        )
        self.nginx_queue.start()

    def get_containers_info(self):

        vhosts_map = {}
        for container_obj in self.docker_client.containers.list(
                filters={'label': 'vhost_primary_domain'}):
            container = container_obj.attrs
            domain = container['Config']['Labels'].get(
                'vhost_primary_domain')
            no_hsts = container['Config']['Labels'].get('no_hsts',
                                                        False)
            enable_ssl = self.check_certificate_files(domain)
            if domain is None:
                continue

            container_networks = container['NetworkSettings'][
                'Networks'].values()
            if len(container_networks) == 1:
                container_ip = container_networks[0].get('IPAddress')
            else:
                container_ip = None

            if not container_ip:
                _logger.warn(
                    'Cannot find the right docker network for container %s.  '
                    'Vhost for this container will not be configured' %
                    container['Name']
                )
                continue

            vhost_data = vhosts_map.get(domain, {'domain': domain})
            endpoints = vhost_data.get('endpoints', [])
            endpoints.append(container_ip)
            vhost_data.update({
                'endpoints': endpoints,
                'no_hsts': no_hsts,
                'enable_ssl': enable_ssl,
            })
            vhosts_map.update({domain: vhost_data})

        return vhosts_map.values()

    def run_certbot_certonly(self, domain):
        if self.check_certificate_files(domain):
            # nothing to do
            return True

        certbot_containers = self.docker_client.containers.list(filters={
            'status': 'running',
            'label': 'certbot_container',
        })
        if not len(certbot_containers):
            raise ContainerNotFoundException(
                'Cannot find certbot container'
            )
        certbot_container = certbot_containers[0]
        _logger.info(
            'Requesting new certificate for domain "%s" with email "%s"' %
            (domain, LETSENCRYPT_EMAIL)
        )
        result = certbot_container.exec_run([
            '/usr/bin/certbot',
            'certonly',
            '--keep-until-expiring',
            '--non-interactive',
            '--agree-tos',
            '--must-staple',
            '--email=%s' % LETSENCRYPT_EMAIL,
            '--webroot',
            '--webroot-path=/srv/webroot/',
            '--domain=%s' % domain,
        ], )
        return result

    @staticmethod
    def inotify_wait_external(path,
                              events=('move', 'create', 'delete', 'modify')):
        cmd = (
            ['inotifywait']
            + ['--event=%s' % e for e in events]
            + ['--recursive', path]
        )
        _logger.debug('lauching cmd %s' % ' '.join(cmd))
        return_code = subprocess.call(cmd)
        return return_code

    @staticmethod
    def check_certificate_files(domain):
        certificate_file = "%s/%s/fullchain.pem" % (CERTBOT_CERT_PATH, domain)
        found = os.path.exists(certificate_file)
        if found:
            _logger.debug(
                'Found certificate file for domain "%s" at "%s"' %
                (domain, certificate_file)
            )
        else:
            _logger.warn(
                'Certificate file not found for domain  "%s" at "%s"' %
                (domain, certificate_file)
            )
        return found

    def render_template(self, context):
        domain = context['domain']
        _logger.debug('Rendering template for domain "%s"' % domain)
        template_file = NGINX_VHOSTS_CONF_PATH + '/odoo-vhost-%s.conf' % domain
        with open(template_file, 'w') as vhosts_conf:
            vhosts_conf.write(self.template_vhosts_conf.render(context))

    @staticmethod
    def cleanup_templates(domains):
        domain_vhost_conf_list = [
            'odoo-vhost-%s.conf' % d for d in domains
            ]
        files_to_remove = filter(
            lambda f: f.endswith('.conf') and f not in domain_vhost_conf_list,
            os.listdir(NGINX_VHOSTS_CONF_PATH)
        )
        for file_name in files_to_remove:
            full_path = os.path.join(NGINX_VHOSTS_CONF_PATH, file_name)
            _logger.debug('Removing nginx conf file "%s"' % full_path)
            os.unlink(full_path)

    def signal_nginx_container(self, send_signal=signal.SIGHUP):
        for container in self.docker_client.containers.list(
                filters={'label': 'proxy_container'}):
            container.kill(signal=send_signal)

    def watch_certificate_tree(self):
        while True:
            event = self.inotify_wait_external(CERTBOT_CERT_PATH)
            _logger.debug("inotifywait retuned '%s'" % event)
            self.nginx_queue.signal()

    def renew_nginx_config(self):
        _logger.debug('Renewing nginx config')
        try:
            vhosts = self.get_containers_info()
            self.cleanup_templates([v.get('domain') for v in vhosts])
            for host in vhosts:
                self.render_template(host)
            self.signal_nginx_container()
        except:
            _logger.exception('Exception in renew_nginx_config')

    def renew_certbot_certs(self):
        _logger.debug('Renewing certbot certs')
        try:
            vhosts = self.get_containers_info()
            for host in vhosts:
                self.run_certbot_certonly(host.get('domain'))
        except:
            _logger.exception('Exception in renew_certbot_certs')

    def listen_docker(self):
        # generate an initial nginx conf at startup
        for event_str in self.docker_client.events(
                filters={'label': 'vhost_primary_domain'}):
            event = json.loads(str(event_str))
            if event.get('Type') != 'container':
                continue
            if event.get('Action') not in ('start', 'die'):
                continue

            _logger.debug('received event %s' % event_str)
            _logger.debug('checking certbot certs')
            self.renew_certbot_certs()
            _logger.debug('signaling nginx')
            self.nginx_queue.signal()

    def start(self):

        # Generate config and certs for already running containers
        self.renew_certbot_certs()
        self.nginx_queue.signal()

        # This processes watches for new certbot certificates
        # When found, nginx gets updated
        certificate_watcher = multiprocessing.Process(
            target=self.watch_certificate_tree)
        certificate_watcher.daemon = True
        certificate_watcher.start()

        # Main process: watch for docker events,
        self.listen_docker()


if __name__ == '__main__':
    root_logger = logging.getLogger()
    root_logger.addHandler(logging.StreamHandler())
    root_logger.setLevel(logging.DEBUG)
    config_obj = NginxCertbotConfigurator()
    config_obj.start()
