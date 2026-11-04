# Data standards requirements

What the portal does with data declared to follow a community standard. Each entry serves part of
the INN Digital Infrastructure Strategy (2026), where both are proposals. The portal supports BIDS
(Patrick, 31 October 2026); both entries stay open until the questions they name are answered. Which
standards the portal supports is a class question whose answers accumulate ([STD-WHICH](../questions/portal.md#std-which)); a second standard
gets its own entries here.

Open entries name the question that settles them in [*INN use cases: decisions*](../questions/use-cases.md) (27 October 2026).
Each test will name the entry it checks (a `Verifies:` line in the module's docstring).

**Status:** *settled* (agreed; tests required), *proposed* (awaiting a functional decision),
*open* (needed by the strategy, not yet decided; no tests yet).

| ID | Requirement | Serves (strategy) | Status |
|-------|----------------------------------------------|-------------------------|--------|
| <a id="std-1"></a>STD-1 | Data declared as BIDS is validated against the BIDS specification when uploaded; data that fails is held in quarantine and the researcher is told what failed. Which standards: [STD-WHICH](../questions/portal.md#std-which). What quarantine holds back: [STD-QUARANTINE](../questions/portal.md#std-quarantine). | [5.1](../strategy/inn-digital-infrastructure-strategy-2026.md#s5-1) main flow step 3; [5.1](../strategy/inn-digital-infrastructure-strategy-2026.md#s5-1) exceptions | open |
| <a id="std-2"></a>STD-2 | Preparing a dataset for release (conversion to BIDS, de-identification) records each step as provenance, and the identifiable source stays on the governed machine ([PX-4](posix-storage.md#px-4)). An approved de-identification step can relax the source's conditions ([D9](../questions/use-cases.md#d9)). | [5.9](../strategy/inn-digital-infrastructure-strategy-2026.md#s5-9) | open |
