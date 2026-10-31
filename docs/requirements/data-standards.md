# Data standards requirements

What the portal does with data declared to follow a community standard. Each entry serves part of
the INN Digital Infrastructure Strategy (2026); both come from its proposals (marked in red there,
not yet agreed), so both are open. Which standards the portal supports is a class question whose
answers accumulate (BIDS is proposed first); a second standard gets its own entries here.

Open entries name the question that settles them in *INN use cases: decisions* (27 October 2026).
Each test will name the entry it checks (a `Verifies:` line in the module's docstring).

**Status:** *settled* (agreed; tests required), *proposed* (awaiting a functional decision),
*open* (needed by the strategy, not yet decided; no tests yet).

| ID | Requirement | Serves (strategy) | Status |
|-------|----------------------------------------------|-------------------------|--------|
| STD-1 | Data declared as BIDS is validated against the BIDS specification when uploaded; data that fails is held in quarantine and the researcher is told what failed. | 5.1 main flow step 3; 5.1 exceptions | open |
| STD-2 | Preparing a dataset for release (conversion to BIDS, de-identification) records each step as provenance, and the identifiable source stays on the governed machine (PX-4). Whether de-identified data keeps the source's conditions is D9. | 5.9 | open |
