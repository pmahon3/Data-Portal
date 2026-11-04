# How the documents fit

Everything the portal does follows from INN's strategy, through a chain of documents. Each level
cites the one above it by link, and every item has a fixed anchor, so a citation lands on the item
itself. The [decision map](https://pmahon3.github.io/Data-Portal/) draws the same chain: click a
level's name to open its documents, or an item to open it here.

| Level | What it holds | Where |
|---|---|---|
| Goal, use case | INN's goals, workflows and use cases | [Strategy](strategy/inn-digital-infrastructure-strategy-2026.md) (`#s4-1`, `#s5-1`) |
| Need | What INN needs decided: who may do what, what is recorded | [Use-case questions](questions/use-cases.md) (`#a1`), [other questions](questions/portal.md), and the questions in [relationships](design/relationships.md#questions) and [access records](design/access-records.md#questions-for-others) |
| Constraint | Facts about the machines and production | [System administrators](questions/posix-system-administrators.md) (`#sa-3`), [production requests](questions/production-requests.md) |
| Requirement | What must hold, testably | [Requirements](requirements/): [access control](requirements/access-control.md), [POSIX storage](requirements/posix-storage.md), [data standards](requirements/data-standards.md), [notifications](requirements/notifications.md) |
| Feature | What people get | [Features](features.md) |
| Design | How it's built, and why | [Designs](design/README.md), [technical-team questions](questions/posix-technical-team.md), [diagrams](diagrams/README.md) |
| Code, test | The code, and the tests that name the requirement they check | This repository; tests name requirements as [AGENT.md](AGENT.md#requirements-and-tests) describes |
| User guide | How to use it | [User guide](user-guide/README.md), published as the [wiki](https://github.com/pmahon3/Data-Portal/wiki) |

The strategy page is generated from its LaTeX source; the others are edited here. The status of each
question and requirement, and what each rests on, is kept in the decision registry, which the map is
built from.
