import Keycloak from "keycloak-js";

// Support both the new uppercase names and the older mixed-case names.
// This avoids login redirect failures when different env files use different names.
const keycloakUrl = process.env.REACT_APP_KEYCLOAK_URL
  || process.env.REACT_APP_KeycloakServerUrl
  || process.env.REACT_APP_KeyCloakServerUrl;
const keycloakRealm = process.env.REACT_APP_KEYCLOAK_REALM
  || process.env.REACT_APP_KeycloakRealm
  || process.env.REACT_APP_KeyCloakRealm;
const keycloakClientId = process.env.REACT_APP_KEYCLOAK_CLIENT_ID
  || process.env.REACT_APP_KeycloakClientId
  || process.env.REACT_APP_KeyCloakClientId;

if (!keycloakUrl || !keycloakRealm || !keycloakClientId) {
  throw new Error("Missing Keycloak frontend configuration.");
}

const keycloak = new Keycloak({
  url: keycloakUrl,
  realm: keycloakRealm,
  clientId: keycloakClientId,
});

// Enable crypto polyfill for local development without HTTPS
keycloak.enableLogging = true;

export default keycloak;
