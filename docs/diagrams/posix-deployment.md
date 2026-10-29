# POSIX Storage: Deployment

What runs on the POSIX machine, as which account, and the permissions that make the operating system
enforce each link's grant. Locally this is the `posix-gateway` container
(`local/docker-compose.posix.yaml`); on a real machine the same layout applies.

The **checked** diagram is compared with the running container by a test: each process's user and
groups, each path's mode and owner, and the socket's mode and owner must match the labels.

```mermaid
%% check: deployment
flowchart TB
    browser(["Browser and portal backend"])

    subgraph container["POSIX machine: file service"]
        web["Web service · process uvicorn · uid 10001 · groups none · port 9100<br/>checks tokens for early refusals; can't open any data file"]
        helper["Privileged helper · process app.helper · uid 0<br/>checks every token itself; grants, places, deletes, revokes"]
        opener["Opener · one per request · uid from 2000000 · group 10010<br/>opens files as the link's temporary ID"]
        sock["socket /run/gateway/helper.sock · mode 0660 · owner 0:10001"]
        data["path /srv/posix/data · mode 0710 · owner 10002:10010<br/>governed files: owner 10002, mode 0600, plus one ACL entry per live link"]
        staging["path /srv/posix/staging · mode 0711 · owner 0:0<br/>one folder per uploading ID, outside the data tree"]
        state["path /srv/posix/.helper · mode 0700 · owner 0:0<br/>which IDs hold which grants (survives restarts)"]
    end

    browser -- "HTTPS, signed links" --> web
    web -- "connects" --> sock
    sock -- "peer must be uid 10001" --> helper
    helper -- "starts" --> opener
    opener -- "read (ACL) / create" --> data
    opener -- "create" --> staging
    helper -- "move into place, delete, ACLs" --> data
    helper -- "records" --> state

    style web fill:#90EE90
    style helper fill:#FF9900
    style opener fill:#FF9900
```

## Accounts

| Account | ID | Role |
|---|---|---|
| `gateway` | 10001 (group 10001) | The web service. No supplementary groups, so it can't pass through data folders. |
| `inndata` | 10002 (group 10002) | Owns the governed files. Nothing runs as it. |
| `posix-traverse` (group) | 10010 | Pass-through permission on data folders. Only openers get it. |
| temporary IDs | 2000000 + | One per approved link; no account entry. Read access through one ACL entry per granted file. |
| root | 0 | The helper. |

## Startup and failure

- The helper starts first, writes a canary file only `inndata` can read, revokes anything already
  expired, and opens its socket.
- The web service starts as `gateway` with `--no-new-privs`. It tries to read the canary: if it can,
  it refuses to start.
- If either process stops, the container stops. If the helper is unreachable, requests get 503;
  nothing falls back to direct access.

---

**Last Updated:** 2026-10-23
**Branch:** posix/stack
