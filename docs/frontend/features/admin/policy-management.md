# Policy Management

Policy management controls which user can perform an action on a storage
resource.

## Policy fields

| Field | Meaning |
| --- | --- |
| Username | User receiving the permission. |
| Instance | Storage instance containing the resource. |
| Resource | One file (`bucket/path/file.ext`), a folder and everything in it (`bucket/folder/*`), or everything on the instance (`*`). |
| Action | `read`, `write`, `delete`, or `admin`. |

Resource paths are literal, not patterns: `bucket/folder/*` covers that folder and
everything in it, any other path names exactly one file, and `*` covers everything.
The backend saves paths without a leading `/` and refuses a `*` anywhere except on its
own or at the end of a folder path. Decisions are made in
`backend/core/services/policies/rules.py`; requirements are in
`docs/requirements/access-control.md`.

## Page flow

1. Load the storage instances available to the current user.
2. Load the policies the current user is allowed to manage.
3. Create a policy from a username, instance, resource, and action.
4. Refresh the policy table after a successful change.

Deleting a policy requires confirmation.

## API calls

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/instances/` | Populate the storage-instance list. |
| `GET` | `/api/policies/` | List manageable policies. |
| `POST` | `/api/policies/` | Create a policy. |
| `DELETE` | `/api/policies/` | Delete a policy. |

The frontend displays friendly usernames and instance names. Policy deletion
currently sends the policy's user UUID, instance UUID, resource, and action back
to the API.

## Authorization

Administrators and project managers can reach the management interface. The
backend determines which instances and policies they may view or change. A
visible form is not proof that a submitted policy is allowed.

Keycloak roles and Casbin policies have different purposes:

- Keycloak controls identity and coarse interface access.
- Casbin controls resource-level permissions.

## Main source file

| Purpose | File |
| --- | --- |
| Page, form, table, and API calls | `frontend/src/components/admin_page/policy_management/index.js` |
