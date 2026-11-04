# Other questions about the portal

Questions raised while building, outside the forms of 27 October 2026. The decision registry records
each one's status and answer.

### <a id="std-which"></a>STD-WHICH. Which data standards does the platform validate and understand?

From strategy [5.1](../strategy/inn-digital-infrastructure-strategy-2026.md#s5-1) and
[5.9](../strategy/inn-digital-infrastructure-strategy-2026.md#s5-9). A class question: answers add
standards, and it stays open. BIDS is the first (Patrick, 2026-10-31); generalizing the validation
seam waits for a second standard.

### <a id="std-quarantine"></a>STD-QUARANTINE. What does quarantine hold back when uploaded data fails its standard's checks?

From [STD-1](../requirements/data-standards.md#std-1). Options:

- Nothing: the failure is recorded and shown to the researcher and administrators.
- Everyone but the uploader and administrators can't see or download it until it's fixed.
- Nobody can download or share it until it's fixed.

### <a id="nt-notify"></a>NT-NOTIFY. How is a researcher told about their data (stored, failed validation, held)?

From strategy [5.1](../strategy/inn-digital-infrastructure-strategy-2026.md#s5-1). Options: in the
portal, by email, or both. Decided by Patrick, 2026-10-30: both
([NT-1](../requirements/notifications.md#nt-1)).

### <a id="dt-withdraw-running"></a>DT-WITHDRAW-RUNNING. Should withdrawing access or consent stop a download that's already running?

From strategy [5.7](../strategy/inn-digital-infrastructure-strategy-2026.md#s5-7) and
[4.7](../strategy/inn-digital-infrastructure-strategy-2026.md#s4-7). Studies of 10 to 100 GB mean a
download can run for hours, up to a day. Options:

- No: a started download finishes, as decided on 2026-10-22 ([streaming spec](../design/streaming-spec.md)), within a limit.
- Yes: withdrawal stops running downloads straight away.
