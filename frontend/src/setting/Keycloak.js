import Keycloak from "keycloak-js";

const cfg = (typeof window !== "undefined" && window.__RUNTIME_CONFIG__) || {};

const keycloakUrl =
  cfg.keycloakUrl ||
  process.env.REACT_APP_KEYCLOAK_URL ||
  process.env.REACT_APP_KeycloakServerUrl ||
  process.env.REACT_APP_KeyCloakServerUrl;
const keycloakRealm =
  cfg.keycloakRealm ||
  process.env.REACT_APP_KEYCLOAK_REALM ||
  process.env.REACT_APP_KeycloakRealm ||
  process.env.REACT_APP_KeyCloakRealm;
const keycloakClientId =
  cfg.keycloakClientId ||
  process.env.REACT_APP_KEYCLOAK_CLIENT_ID ||
  process.env.REACT_APP_KeycloakClientId ||
  process.env.REACT_APP_KeyCloakClientId;

if (!keycloakUrl || !keycloakRealm || !keycloakClientId) {
  throw new Error("Missing Keycloak frontend configuration.");
}

const keycloak = new Keycloak({
  url: keycloakUrl,
  realm: keycloakRealm,
  clientId: keycloakClientId,
});

keycloak.enableLogging = true;

export default keycloak;
