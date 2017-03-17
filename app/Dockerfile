FROM alpine

# basic flask environment
RUN apk add --no-cache py2-pip \
    && pip2 install --upgrade pip \
    && pip2 install flask


# expose web server port
# only http, for ssl use reverse proxy
EXPOSE 8069

# copy config files into filesystem
ADD app.py /

# exectute start up script
CMD [ "python", "/app.py" ]
