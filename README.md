# docker-nginx-le-companion
Auto configure your nginx reverse proxy container with LetsEncrypt support


Installation
------------

* install docker and docker-compose
* use docker-compose build
* generate dhparam.pem:
```
mkdir -p /srv/nginx/
openssl dhparam 4096 -out /srv/nginx/dhparam.pem
```
* configure the ```vhost_primary_domain``` label in the compose file to something suitable so that web request from internet reach your machine
* docker-compose up
* wait a few moments and connect to your new TLS service

