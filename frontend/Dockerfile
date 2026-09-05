# ---- Stage 1: build React app ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Copy app source (includes .env files)
COPY . .

# Build the app. Keycloak URL/realm/client are injected at container start via env.js.
RUN npm run build

# ---- Stage 2: Nginx runtime ----
FROM nginx:1.21.6-alpine
# needed for envsubst in entrypoint.sh
RUN apk add --no-cache gettext

COPY --from=build /app/build/ /usr/share/nginx/html/
COPY nginx/conf/nginx.conf.template /etc/nginx/conf.d/default.conf.template
COPY nginx/env.js.template /etc/nginx/templates/env.js.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
