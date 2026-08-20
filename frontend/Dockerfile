# ---- Stage 1: build React app ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Copy app source (includes .env files)
COPY . .

# Provided by the frontend CI/CD pipeline (or local Docker Compose build args)
ARG REACT_APP_KEYCLOAK_URL
ARG REACT_APP_KEYCLOAK_REALM=ams-portal
ARG REACT_APP_KEYCLOAK_CLIENT_ID=ams-portal-ui

# Convert build args to env vars for React build process
ENV REACT_APP_KeyCloakServerUrl=$REACT_APP_KEYCLOAK_URL
ENV REACT_APP_KeyCloakRealm=$REACT_APP_KEYCLOAK_REALM
ENV REACT_APP_KeyCloakClientId=$REACT_APP_KEYCLOAK_CLIENT_ID

# Build the app
RUN npm run build

# ---- Stage 2: Nginx runtime ----
FROM nginx:1.21.6-alpine
# needed for envsubst in entrypoint.sh
RUN apk add --no-cache gettext

COPY --from=build /app/build/ /usr/share/nginx/html/
COPY nginx/conf/nginx.conf.template /etc/nginx/conf.d/default.conf.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
