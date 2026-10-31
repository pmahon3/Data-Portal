# Data Standards

**Last updated:** 2026-10-31

How uploaded data is checked against the standard it declares (STD-1). A folder declares a standard
by holding that standard's marker file at its root (BIDS: `dataset_description.json`), so data
placed on a machine directly declares it the same way. When an upload completes, every declared
dataset it touched is checked as a whole. A failure puts the dataset in quarantine and the upload's
response names what failed; a later pass takes it out.

```mermaid
graph LR
    Browser[Browser]

    subgraph "Backend"
        Complete[Upload complete<br/>file or folder]
        Seam[Standards seam<br/>finds declared datasets]
        Validators[Validators<br/>one per standard]
        Record[Record result]
    end

    Tree[(PostgreSQL<br/>file tree)]
    Mongo[(MongoDB<br/>dataset-checks)]

    Browser -->|POST .../upload/complete| Complete
    Complete -->|uploaded keys| Seam
    Seam -->|marker files above the keys,<br/>then every file in each dataset| Tree
    Seam -->|paths relative to the dataset| Validators
    Validators -->|problems| Record
    Record -->|passed, or quarantined with findings| Mongo
    Complete -->|checks: dataset, standard,<br/>quarantined, first 100 findings| Browser

    style Seam fill:#4A90E2
    style Mongo fill:#47A248
    style Tree fill:#A9C6E8
```

Checks read names and layout from the file tree only, so no file contents move. Checks that need
the contents (sidecar files, image headers) will run beside the data on the storage machine.

Still open:
- **What quarantine holds back (N-QUARANTINE).** Until it's decided, quarantine is recorded and
  shown, and holds nothing back.
- **Which standards the portal checks (E-STD).** Each standard plugs in a validator.

| Setting | Meaning |
|---|---|
| `MONGO_DATASET_CHECK_COLLECTION` | Collection for results (default `dataset-checks`), one per dataset and standard |
