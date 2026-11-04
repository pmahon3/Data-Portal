# Designs

How features are built, and why. Each design names the requirements it implements. Choices made in
conversation, without a design note of their own, are in the [decision log](decision-log.md).

| Design | What it covers |
|---|---|
| [Policy conditions](policy-conditions.md) | Exclusions, file types and end dates on a policy ([AC-6](../requirements/access-control.md#ac-6), [AC-8](../requirements/access-control.md#ac-8), [AC-10](../requirements/access-control.md#ac-10)) |
| [Use-case instances](use-case-instances.md) | Concrete cases from INN's studies behind the permission model, and choosing from the file tree |
| [Check access](check-access.md) | Can this person do this, and which policy says so |
| [Policy preview](policy-preview.md) | What a policy will allow, before it's saved |
| [Explaining access rules](explaining-access-rules.md) | Research behind the access pages of the user guide, and the product follow-ups |
| [Access records](access-records.md) | What is recorded, how changes are detected, how it scales ([AC-9](../requirements/access-control.md#ac-9)) |
| [Relationships](relationships.md) | Access through research relationships ([AC-12](../requirements/access-control.md#ac-12)) |
| [Streaming spec](streaming-spec.md) | POSIX downloads streamed on demand, and the file service contract |
| [Decision log](decision-log.md) | Smaller design decisions, one anchor each |

The POSIX design itself is in `docs/posix/README.md` on the `posix/stack` branch.
