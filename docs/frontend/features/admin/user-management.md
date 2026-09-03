# User Management

User management lists portal identities and sends user changes to the backend,
which manages them in Keycloak.

## Available actions

| Action | Behavior |
| --- | --- |
| List users | Shows the username, email, and non-default roles. |
| Create | Creates a Keycloak user from the form. |
| Delete | Removes a user after confirmation. The button is admin-only. |

The user form contains:

- username;
- password;
- full name;
- email; and
- comma-separated roles.

Username, password, and email are required by the current form.

The section is currently labelled **Create / Update User**, but the API creates
new users only. Submitting an existing username returns a conflict.

## API calls

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/users/` | List users visible to the current user. |
| `POST` | `/api/users/` | Create a user. |
| `DELETE` | `/api/users/{username}` | Delete a user. |

All requests include a Keycloak bearer token. The backend determines whether the
caller may view or change the requested user.

## Role behavior

Administrators and project managers can list and create users. Project managers
cannot create a user with the `admin` role. Only administrators receive delete
controls in this management page.

Keycloak realm roles control coarse application access. They do not replace
Casbin policies for storage resources.

## Main source file

| Purpose | File |
| --- | --- |
| Page, form, table, and API calls | `frontend/src/components/admin_page/user_management/index.js` |
