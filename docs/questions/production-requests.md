# Requests for whoever has production access

The questions as put on 27 October 2026 to whoever has access to the portal's production databases. Some background has moved on since; the decision registry records each question's status and answer.

### Why these questions

One piece of work is waiting on data only production access can provide. It changes nothing in production: it only reads.

Background for every item: docs/posix/README.md and docs/diagrams/posix-*.md on branch posix/stack, and [the file service contract](../design/streaming-spec.md).

### <a id="pr-1"></a>PR-1. Report how the stored access rules would convert (access-control rework, !166)

**What:** Before !166 is deployed, its conversion of stored rules from regular expressions to literal paths has to be checked against production: which rules convert automatically and which need someone to decide. Report only; nothing is changed.

**How:** Either run python -m core.services.policies.convert_paths (without --apply it only reports) in a production backend container with the !166 code, or mongoexport the casbin_rule collection and run the report against a copy. The report lists user and instance IDs and paths, so it should travel securely.

**Deliver to:** Patrick, by a secure route (not email). The actual conversion (--apply) runs later, with the deployment, once the report is signed off.
