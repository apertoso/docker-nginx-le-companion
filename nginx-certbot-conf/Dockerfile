FROM alpine

# copy files into filesystem
ADD nginx_certbot_conf.py requirements.txt /
ADD templates/*.conf.j2 /templates/

# basic flask environment
RUN apk add --no-cache inotify-tools py2-pip \
    && pip2 install --upgrade pip \
    && pip2 install -r requirements.txt

# need docker socket
VOLUME /var/run/docker.sock
VOLUME /srv/nginx-vhosts-conf.d/

# exectute start up script
CMD [ "python", "/nginx_certbot_conf.py" ]
