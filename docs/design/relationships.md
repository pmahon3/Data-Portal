# Access through research relationships: regrouping the access code (design, reviewed: false)

2026-11-02. Patrick and agent, from a review of what projects do. Strategy: *Keeping access in step
with research relationships* (correspondence; researcher-driven; bounded delegation; relationship
lifecycles; legibility; governance sets the bounds). Registry: `DS-relationship-grants` and the
questions under it.

## What projects do today

A project is a Keycloak group with a `managers` subgroup, linked to whole storage instances (MongoDB
`project-instance-associations`). It decides who sees the admin screens, whose access a manager may
change and on which instances, which instances a manager sees, and who gets end-date reminders. It
grants nothing: members have no access until someone writes per-person policies, and leaving
removes none. Its reach is whole instances. A manager can list and create every user, whatever the
project. In practice it is a delegated-administration scope.

## The groupings

| Layer | About | Today |
|---|---|---|
| Administration scope | who may administer whose access, on what storage | projects |
| Research relationship | a study, collaboration or agreement: members, terms, a lifespan | nothing (an `Agreement` model, never built) |
| Data | a dataset or folder: where it is, its standard, its conditions | folders, standard detection, policy conditions |
| Individual grant | one person, one path, one action | policies |
| Person | can this person do this, and why | Check Access |

## The move: a group can hold grants

A policy's subject may be a project as well as a person. Then:

- **Membership gives access**: the checker reads the person's rules and their projects' rules (one
  wider query in `rules_for`); `Rule`, `Checker` and the conditions are unchanged.
- **Leaving removes access**, with nothing to clean up.
- **The project's grants are its data scope**: the folders a study holds are the paths its grants
  name. No dataset table; the instance links become derivable.
- **Its terms ride on its grants**: end dates, exclusions, file types; reminders already work.
- **Bounded delegation is one rule**: a project manager manages membership, and grants only within
  paths the project's grants cover.
- **Legibility is a query**: a grant is via project X or direct. Check Access says which; a project
  page lists grants and members; direct per-person policies show as exceptions.

## Coupling

Membership comes from Keycloak groups through `AbstractProjectManager`, which `KeycloakProjectManager`
implements. To keep it replaceable:

1. Grants name a project by its stable ID, never its name (renames exist).
2. One interface method answers "which projects is this person in, and which do they manage"; the
   checker and every endpoint ask only it. Today three places parse the token's `projects` claim
   themselves (`AppRouter.js`, `instances.py`, `projects.py`), and `can_manage_instance_for_user`
   takes the raw token: these move behind the method.
3. Terms stay on our grants, never in Keycloak.
4. Membership is read through the seam (briefly cached), not from the token, so removal doesn't wait
   for a token refresh and no claim mapper is needed.

If studies need roles, membership dates or approval states, our own membership table becomes a
second implementation behind the same seam (`REL-MEMBERSHIP-STORE`, deferred).

## Order (one MR each; the portal works after each)

1. **Cuts**: Casbin's enforcer (nothing reads it; storage format kept), `POST /api/policies/validate`
   (Check Access replaces it), the `Agreement` stubs, the unused `actions` list; the who-has-access
   branch is dropped.
2. **Project grants**: a policy may name a project; the checker includes the person's projects.
3. **Bounded delegation**: through the one membership method; scopes managers' user listing and creation.
4. **Legibility**: a project page (grants and terms, members, direct exceptions); Check Access says
   "via project X". Tree markers (an icon on folders a policy names) are skipped (Patrick,
   2026-11-02): with many policies nearly every folder carries one, and every listing would read the
   policy store; Check Access answers the question.
5. **Retire the instance links** once nothing reads them.

Steps 2 to 5 wait on `REL-MEMBERSHIP-ACCESS`. Step 1 doesn't.

## Scale

- Checker: the person's rules plus their projects' rules, one indexed query (`v0` in a short list);
  membership lookup cached per person for a short time.
- Project page: one indexed read of the project's grants; names only when asked.

## Questions

| ID | Question | Owner |
|---|---|---|
| <a id="rel-membership-access"></a>REL-MEMBERSHIP-ACCESS | Does project membership confer access, and who may create a project's grants (administrators or stewards only; managers manage membership)? | leadership |
| <a id="rel-removal-latency"></a>REL-REMOVAL-LATENCY | How soon must removing someone from a project end their access? | privacy |
| <a id="rel-project-name"></a>REL-PROJECT-NAME | What do we call it: "project", "study", or both (a study inside a project)? | patrick |
| <a id="rel-membership-store"></a>REL-MEMBERSHIP-STORE | Where does membership live once it needs roles, dates or approval? (deferred) | team |
