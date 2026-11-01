# Storage, projects and users

For administrators and project managers. Giving people access to data is on its own page:
[Giving people access](policies.md).

## Storage connections
<!-- claim: AC-5; tests: test_a_new_instance_grants_its_creator_a_rule_the_portal_accepts -->

**Connection Management** lists the storage the portal reads from, one card per instance.

![The storage instances page: the create form and one instance's card](../images/storage-management.png)

| Action | Administrator | Project manager |
|---|---|---|
| Add an instance | Yes | Yes, for projects you manage |
| Sync it | Yes | Yes, for projects you manage |
| Rename it | Yes | No |
| Delete it | Yes | No |

- **Adding an instance** needs a name, the storage address and its access and secret keys. The
  portal checks it can connect before saving. Whoever adds it is given full access to it.
- **Sync** reads what's in storage, so files added outside the portal appear in it. It can take a
  while on a large store.
- **Deleting an instance** removes it, its file list and every policy on it from the portal. The
  files in storage are left alone.

Secret keys are masked whenever an instance's settings are shown.

## Projects

**Project Management** groups people and storage under a project. Each project has users,
managers, and the storage instances assigned to it.

| Action | Administrator | Project manager |
|---|---|---|
| Add or remove a project's users | Yes | Yes |
| Create or delete a project | Yes | No |
| Add or remove managers | Yes | No |
| Assign storage to a project | Yes | No |

Project managers see the same admin panel, but can act only on the projects they manage.

## Users

**User Management** lists portal accounts and creates new ones (username, password, name, email
and roles). Project managers can't create administrators; only administrators can delete
accounts.

A new account can't see any data until it's given access: see [Giving people access](policies.md).
