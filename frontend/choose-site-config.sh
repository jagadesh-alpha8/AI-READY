#!/bin/sh
# Runs at container start (nginx image: /docker-entrypoint.d/*.sh).
# HTTPS needs the certificate certbot creates on the VM; without it nginx
# would refuse to start and take the whole site down. So: certificate
# present -> HTTPS config (port 80 redirects); absent -> plain HTTP.
set -e
CERT=/etc/letsencrypt/live/ai.ingageedutech.com/fullchain.pem
if [ -f "$CERT" ]; then
    cp /etc/nginx/site/https.conf /etc/nginx/conf.d/default.conf
    echo "choose-site-config: certificate found, serving HTTPS"
else
    cp /etc/nginx/site/http.conf /etc/nginx/conf.d/default.conf
    echo "choose-site-config: no certificate at $CERT, serving plain HTTP"
fi
