import Keycloak from "keycloak-js";

const keycloak = new Keycloak({
  url: process.env.REACT_APP_KeycloakServerUrl,// Keycloak base URL
  realm: process.env.REACT_APP_KeycloakRealm, // realm name
  clientId: process.env.REACT_APP_KeycloakClientId, // client ID
});

// Enable crypto polyfill for local development without HTTPS
keycloak.enableLogging = true;

export default keycloak;