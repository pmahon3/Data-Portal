import keycloak from '../setting/Keycloak';

/**
 * Returns authorization headers with the current Keycloak token, 
 * refreshing it if necessary.
 */
export const getAuthHeaders = async () => {
  // Instead of the React 'initialized' state, we check if the raw keycloak instance 
  // has a token and is authenticated before trying to update it.
  if (!keycloak || !keycloak.authenticated) return {};
  
  try {
    await keycloak.updateToken(30);
  } catch (err) {
    // Token refresh failed or not initialized
  }
  
  return keycloak?.token ? { Authorization: `Bearer ${keycloak.token}` } : {};
};
