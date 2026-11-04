# Check access: can this person do this, and which policy says so (design, reviewed: false)

2026-11-02 (agent; reversible). Registry: `DS-check-access` (parents AC-1, AC-3). From the research
behind *How access works*: AWS's policy simulator, GCP's Policy Troubleshooter and Azure's "check
access" each take who, what and which action, and return the decision and the grant responsible.

## What it does

An administrator, or a project manager for people in their projects, gives a person, a storage
instance, a path and an action. The portal answers:

- **Allowed or not**, decided exactly as a real request is (`Checker`), today.
- **Because of:** each of the person's policies that allows it (there may be several; policies add up).
- **For a folder** (a path ending in `/`): whether it appears in the person's tree, and that seeing
  it doesn't allow acting on it.
- **When refused:** that none of the person's policies allows it. Policies don't deny, so there's
  nothing else to show.

## The seam

`rules.covering(rules, path, action)`: the rules that allow the action on the path. It is the
question three features ask (this tool, the who-has-access view, the save preview), so it lives
beside `rule_allows` and a property test checks it against `Checker`. The policy manager gains
`rules_for(user, instance)`, the read `checker()` already does, so the tool sees exactly what a
request sees.

## Who may use it

Exactly who may list that person's policies: administrators for anyone; a project manager only
for people in a project they manage (`can_manage_instance_for_user`, as saving a policy does). Others
get 403. Unknown person or instance: 404. The person's own policies only, never other people's.

## Scale

One indexed read of one person's policies on one instance (the same read every request does) and a
check per policy: under a millisecond for thousands of policies (AC-11's target for a check). Nothing
is stored.

## Not now

A self-service "view my access" for researchers, and starting from an error a refused user just saw
(GCP): both fit the same endpoint later.
