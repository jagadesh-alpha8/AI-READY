FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Two site configs; choose-site-config.sh picks one at container start:
# HTTPS when the Let's Encrypt certificate is mounted, plain HTTP otherwise.
COPY nginx.conf /etc/nginx/site/http.conf
COPY nginx-https.conf /etc/nginx/site/https.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY choose-site-config.sh /docker-entrypoint.d/40-choose-site-config.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-choose-site-config.sh \
    && chmod +x /docker-entrypoint.d/40-choose-site-config.sh
EXPOSE 80 443
