# Authentication Sequence Diagrams

## User Login Flow

Current OAuth2/OIDC login flow using Keycloak.

```mermaid
sequenceDiagram
    actor User
    participant Frontend as React Frontend
    participant Keycloak
    participant Backend as FastAPI Backend

    User->>Frontend: Open app
    Frontend->>Keycloak: Check for an existing SSO session

    alt Existing Keycloak SSO session
        Keycloak-->>Frontend: Return tokens
    else No Keycloak SSO session
        Frontend-->>User: Show login button
        User->>Frontend: Click Login
        Frontend->>Keycloak: Redirect to login
        User->>Keycloak: Enter credentials
        Keycloak-->>Frontend: Redirect to /app with authorization code
        Frontend->>Keycloak: Exchange authorization code for tokens
        Keycloak-->>Frontend: Return tokens
    end

    Frontend->>Frontend: Keep tokens in memory and route by claims
    Frontend->>Keycloak: Refresh token when near expiry
    Frontend->>Backend: API request with bearer token
    Backend->>Keycloak: Fetch OIDC configuration and JWKS keys
    Backend->>Backend: Validate JWT and apply endpoint authorization
    Backend-->>Frontend: API response
```

## Token Validation Flow

How the backend validates Keycloak access tokens.

```mermaid
sequenceDiagram
    participant Frontend
    participant Backend as FastAPI Backend
    participant Keycloak

    Frontend->>Backend: API request with bearer token
    Backend->>Backend: Extract JWT
    Backend->>Keycloak: Fetch OIDC configuration
    Keycloak-->>Backend: Return JWKS URI
    Backend->>Keycloak: Fetch public signing key
    Keycloak-->>Backend: Return JWKS keys
    Backend->>Backend: Verify RS256 signature, issuer, and expiry

    alt Token Valid
        Backend->>Backend: Read claims and check endpoint permissions
        alt Authorized
            Backend-->>Frontend: API response
        else Insufficient permissions
            Backend-->>Frontend: 403 Forbidden
        end
    else Token missing or invalid
        Backend-->>Frontend: 401 Unauthorized
    end
```

## Admin Operation Flow

Authorization flow for admin-only operations.

```mermaid
sequenceDiagram
    actor Admin
    participant Frontend
    participant Backend
    participant Keycloak
    participant Casbin

    Admin->>Frontend: Request Admin Operation<br/>(e.g., Create User)
    Frontend->>Backend: POST /api/admin/user/<br/>Authorization: Bearer {token}

    Backend->>Backend: Extract JWT
    Backend->>Keycloak: Validate Token
    Keycloak->>Backend: Valid Token<br/>+ User Claims

    Backend->>Backend: Extract Roles<br/>(realm_access.roles)

    alt Has Admin Role
        Backend->>Casbin: Check Policy<br/>(user_id, admin, create_user)
        Casbin->>Backend: ALLOW

        Backend->>Keycloak: Admin API Call<br/>Create User
        Keycloak->>Backend: User Created<br/>{user_id, email}

        Backend->>Casbin: Add Default User Policies<br/>(grant access to new user)
        Casbin->>Backend: Policies Added

        Backend->>Frontend: 201 Created<br/>{message, user_data}
        Frontend->>Admin: Success Message

    else No Admin Role
        Backend->>Casbin: Check Policy
        Casbin->>Backend: DENY
        Backend->>Frontend: 403 Forbidden<br/>Insufficient permissions
        Frontend->>Admin: Error Message
    end
```

## Token Refresh Flow

Refreshing expired access tokens without re-login.

```mermaid
sequenceDiagram
    participant Frontend
    participant Backend
    participant Keycloak

    Frontend->>Backend: API Request<br/>Authorization: Bearer {expired_token}
    Backend->>Backend: Validate Token
    Backend->>Frontend: 401 Unauthorized<br/>Token Expired

    Frontend->>Frontend: Check Refresh Token<br/>Exists and Valid?

    alt Has Valid Refresh Token
        Frontend->>Keycloak: POST /token<br/>grant_type=refresh_token<br/>refresh_token={refresh_token}

        Keycloak->>Keycloak: Validate Refresh Token
        Keycloak->>Frontend: New Access Token<br/>+ New Refresh Token

        Frontend->>Frontend: Store New Tokens
        Frontend->>Backend: Retry Original Request<br/>Authorization: Bearer {new_token}
        Backend->>Backend: Validate New Token
        Backend->>Frontend: 200 OK<br/>Response Data

    else No Refresh Token or Invalid
        Frontend->>Frontend: Clear Tokens
        Frontend->>Frontend: Redirect to Login
    end
```

## User Management Flow

Creating a new user through the admin API.

```mermaid
sequenceDiagram
    actor Admin
    participant Backend
    participant Keycloak
    participant PolicyMgr
    participant Casbin

    Admin->>Backend: POST /api/admin/user/<br/>{username, email, password}

    Backend->>Backend: Validate Admin Token
    Backend->>Casbin: Check admin permission
    Casbin->>Backend: ALLOW

    Backend->>Keycloak: POST /admin/realms/{realm}/users<br/>{username, email, enabled: true}
    Keycloak->>Keycloak: Create User Account
    Keycloak->>Backend: 201 Created<br/>{user_id}

    Backend->>Keycloak: PUT /admin/realms/{realm}/users/{user_id}/reset-password<br/>{value: password, temporary: false}
    Keycloak->>Backend: 204 No Content

    Backend->>Keycloak: POST /admin/realms/{realm}/users/{user_id}/role-mappings/realm<br/>[{name: "user"}]
    Keycloak->>Backend: 204 No Content

    Backend->>PolicyMgr: Add Default Policies<br/>(user basic access)
    PolicyMgr->>Casbin: Add Policy Rules
    Casbin->>PolicyMgr: Policies Added

    Backend->>Admin: 201 Created<br/>{user_id, username, email}
```

## Logout Flow

Proper session termination and token revocation.

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Backend
    participant Keycloak

    User->>Frontend: Click Logout

    Frontend->>Backend: POST /api/auth/logout<br/>Authorization: Bearer {token}
    Backend->>Backend: Extract Token

    Backend->>Keycloak: POST /logout<br/>id_token_hint={id_token}<br/>post_logout_redirect_uri={uri}

    Keycloak->>Keycloak: Revoke Session
    Keycloak->>Keycloak: Invalidate Tokens
    Keycloak->>Backend: Redirect to URI

    Backend->>Frontend: 200 OK<br/>Logout Successful

    Frontend->>Frontend: Clear Local Tokens<br/>(SessionStorage/Memory)
    Frontend->>Frontend: Clear User State
    Frontend->>User: Redirect to Login Page
```

---

## Authentication Patterns

### Pattern 1: Authorization Code Flow (Standard)
- **Use Case:** Web applications with a backend
- **Security:** Most secure, code exchange prevents token interception
- **Implementation:** Current system uses this for user authentication

### Pattern 2: Client Credentials Flow
- **Use Case:** Service-to-service communication
- **Security:** Machine authentication, no user context
- **Implementation:** Backend uses this for Keycloak admin operations
- **Details:** See [Backend Initialization](../../backend/docs/INITIALIZATION.md)

### Pattern 3: Resource Owner Password Flow
- **Use Case:** Trusted first-party apps
- **Security:** Less secure, credentials exposed to client
- **Status:** Used only for admin CLI token in init scripts
- **Details:** See [Backend Initialization](../../backend/docs/INITIALIZATION.md)

---

## Security Considerations

### Token Storage
- ✅ **Memory/SessionStorage** - Current implementation
- ❌ **LocalStorage** - Vulnerable to XSS attacks
- ✅ **HTTP-only Cookies** - Alternative secure option

### Token Validation
- ✅ **JWKS-based** - Fast, no network call per request
- ✅ **Token Introspection** - Real-time revocation check
- ⚠️ **Signature Verification** - Always verify, never trust client

### Authorization Checks
- ✅ **Backend enforcement** - Never trust frontend
- ✅ **Casbin policies** - Fine-grained control
- ✅ **Role-based + Resource-based** - Defense in depth

---

**Last Updated:** 2026-08-18
