# Notification requirements

What the portal tells researchers about their data. Each entry serves part of the INN Digital
Infrastructure Strategy (2026). Each test names the entry it checks (a `Verifies:` line in the
module's docstring).

How researchers are told was decided on 31 October 2026 (Patrick): both in the portal and by email.

**Status:** *settled* (agreed; tests required), *proposed* (awaiting a functional decision),
*open* (needed by the strategy, not yet decided; no tests yet).

| ID | Requirement | Serves (strategy) | Status |
|------|----------------------------------------------|-------------------------|--------|
| <a id="nt-1"></a>NT-1 | A researcher is told, in the portal and by email, when their upload is stored, and how many files failed if some weren't. The email names no files, since file names can identify participants. Decided by N-NOTIFY. | 5.1 main flow step 5; 5.1 exceptions | proposed |

[NT-1](#nt-1) covers storage today. The strategy's other notifications (a failed format check, data held in
quarantine for missing consent or a failed BIDS check) use the same mechanism once those checks exist.
