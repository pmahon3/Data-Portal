# POSIX Storage: Component Architecture

How the portal reaches data held on POSIX machines (INN and ImageTech). The narrative, decisions and
limits are in [docs/posix/README.md](../posix/README.md). Diagrams marked **checked** are compared with
the code by tests; see [How the diagrams are checked](../posix/README.md#how-the-diagrams-are-checked).

---

## System Overview

Where each piece runs. The portal never holds the data; it decides access and signs links. The file
service runs on the POSIX machine itself.

```mermaid
flowchart LR
    browser(["Browser"])

    subgraph portal["Portal (RCG cluster)"]
        frontend["Frontend<br/>React"]
        backend["Backend<br/>FastAPI"]
        keycloak["Keycloak<br/>identity"]
        mongo[("MongoDB<br/>instances, policies")]
        postgres[("PostgreSQL<br/>file tree")]
    end

    subgraph machine["POSIX machine (INN, ImageTech)"]
        web["File service: web<br/>unprivileged"]
        helper["File service: helper<br/>root"]
        opener["Opener<br/>runs as the link's temporary ID"]
        data[("Governed data")]
    end

    browser --> frontend
    browser -- "API calls" --> backend
    browser -- "signed link" --> web
    backend -- "service calls (metadata, delete)" --> web
    web -- "public key" --> backend
    backend --- keycloak
    backend --- mongo
    backend --- postgres
    web -- "Unix socket" --> helper
    helper -- "starts" --> opener
    opener -- "opens" --> data
    helper -- "places, deletes, ACLs" --> data

    style frontend fill:#61DAFB
    style backend fill:#4A90E2,color:#fff
    style keycloak fill:#E94B3C,color:#fff
    style mongo fill:#FFD700
    style postgres fill:#4A90E2,color:#fff
    style web fill:#90EE90
    style helper fill:#FF9900
    style opener fill:#FF9900
    style data fill:#FF9900
```

---

## File Service Modules (checked)

`storage-gateway/app`. Each solid arrow is a Python import, and every import between these modules
is drawn: a test fails if an arrow is missing or extra. The web side (`main`, `broker`) never imports
the privileged side (`helper`, `acl`, `opener`, `layout`); import-linter enforces that separately.
Dotted arrows are runtime relationships, not imports.

```mermaid
%% check: gateway-modules
flowchart TB
    subgraph webside["Web service (uid 10001, can't read the data)"]
        main["app/main<br/>HTTP endpoints, access log, startup check"]
        broker["app/broker<br/>HelperAccess (deployed), DirectAccess (tests)"]
    end
    subgraph shared["Shared"]
        auth["app/auth<br/>token checks"]
        config["app/config<br/>settings, canary name"]
        files["app/files<br/>no-follow walk, byte ranges, validators"]
    end
    subgraph privileged["Privileged helper (root)"]
        helper["app/helper<br/>tokens, temporary IDs, grants, staging, sweeper, audit"]
        acl["app/acl<br/>POSIX ACLs through descriptors"]
        layout["app/layout<br/>data-layout check and conversion"]
    end
    opener["app/opener<br/>opens files as the link's temporary ID"]
    zipstream["app/zipstream<br/>streaming ZIP core (not wired yet)"]

    main --> auth
    main --> broker
    main --> config
    main --> files
    broker --> files
    helper --> acl
    helper --> auth
    helper --> config
    helper --> files
    layout --> acl
    opener --> files

    broker -. "Unix socket, one request per connection" .-> helper
    helper -. "starts as the link's ID" .-> opener

    style main fill:#90EE90
    style broker fill:#90EE90
    style helper fill:#FF9900
    style acl fill:#FF9900
    style layout fill:#FF9900
    style opener fill:#FF9900
```

---

## Backend POSIX Modules (checked)

The parts of the portal backend that issue POSIX links. Solid arrows are imports among these modules,
all of them; the dotted arrow is a runtime call.

```mermaid
%% check: backend-posix-modules
flowchart LR
    s3_endpoints["api/v0_1/endpoints/s3_endpoints<br/>download-url, upload, delete, bundle (multi-file refused for POSIX)"]
    storage_links_endpoint["api/v0_1/endpoints/storage_links<br/>GET /api/storage-links/jwks.json"]
    agent_factory["core/storage_agents/agent_factory"]
    abstract_storage_agent["core/storage_agents/abstract_storage_agent"]
    posix_agent["core/storage_agents/posix_agent<br/>PosixStorageAgent: namespace, links, service calls"]
    s3_agent["core/storage_agents/s3_agent"]
    storage_links["core/services/storage_links"]
    signer["core/services/storage_links/signer<br/>LinkSigner: RS256, sub = portal user"]

    agent_factory --> abstract_storage_agent
    agent_factory --> posix_agent
    agent_factory --> s3_agent
    posix_agent --> abstract_storage_agent
    posix_agent --> storage_links
    s3_agent --> abstract_storage_agent
    storage_links --> signer
    storage_links_endpoint --> storage_links

    s3_endpoints -. "instance agent, via InstanceManager" .-> posix_agent

    style posix_agent fill:#4A90E2,color:#fff
    style signer fill:#FFD700
```

---

**Last Updated:** 2026-10-23
**Branch:** feature/posix-port
