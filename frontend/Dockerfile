# Hearsay console image: build the SPA, serve it with nginx, proxy API calls.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# Self-signed TLS cert so the live-mic feature (which needs a secure context)
# works when hitting the host directly. Browsers will warn once for the
# untrusted issuer; replace with a real cert/key at /etc/nginx/certs to remove
# the warning. SANs cover the host alias and localhost.
RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
        -keyout /etc/nginx/certs/hearsay.key \
        -out /etc/nginx/certs/hearsay.crt \
        -subj "/CN=3090.zero" \
        -addext "subjectAltName=DNS:3090.zero,DNS:localhost,IP:127.0.0.1"
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80 443
