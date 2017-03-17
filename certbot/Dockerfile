# inspired from
# https://github.com/sebble/docker-images/blob/master/letsencrypt-certbot/Dockerfile

FROM alpine

RUN apk add --no-cache certbot

VOLUME /etc/letsencrypt
VOLUME /var/lib/letsencrypt
VOLUME /srv/webroot/

COPY crontab /var/spool/cron/crontabs/certbot-renew

## Default: Run this container with auto-renew twice daily
CMD /usr/sbin/crond -fd15