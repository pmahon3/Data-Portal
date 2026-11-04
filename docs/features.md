# Features

What the portal offers or will offer, each named for what a researcher or administrator gets. A
feature serves the requirements listed with it. The decision registry links each feature here, and
its designs and code to it. The requirement registers in [requirements/](requirements/) say what must
hold; this page groups them into what people use.

| Feature | What you get | Serves |
|---|---|---|
| <a id="feat-upload"></a>FEAT-upload | Upload files and folders. An existing feature. | [PX-1](requirements/posix-storage.md#px-1), [PX-6](requirements/posix-storage.md#px-6); strategy [5.1](strategy/inn-digital-infrastructure-strategy-2026.md#s5-1) |
| <a id="feat-authz"></a>FEAT-authz | Access control that matches the rules: you see and act on only what your policies give. | [AC-1](requirements/access-control.md#ac-1) to [AC-5](requirements/access-control.md#ac-5) |
| <a id="feat-bundle-security"></a>FEAT-bundle-security | A prepared multi-file download can be fetched only by the person who asked for it, and only while they're still allowed. | [AC-3](requirements/access-control.md#ac-3) |
| <a id="feat-multifile-download"></a>FEAT-multifile-download | Several files as one download: bundled for object storage, streamed as one ZIP from a POSIX machine. | [PX-13](requirements/posix-storage.md#px-13), [PX-14](requirements/posix-storage.md#px-14) |
| <a id="feat-posix-access"></a>FEAT-posix-access | Browse, download, upload and delete files on POSIX machines through the portal. | [PX-1](requirements/posix-storage.md#px-1), [PX-2](requirements/posix-storage.md#px-2), [PX-3](requirements/posix-storage.md#px-3), [PX-5](requirements/posix-storage.md#px-5) to [PX-7](requirements/posix-storage.md#px-7) |
| <a id="feat-posix-os-enforcement"></a>FEAT-posix-os-enforcement | With administrator access on a machine: its operating system enforces each approval too, and its own records trace each access to a person. | [PX-8](requirements/posix-storage.md#px-8) to [PX-10](requirements/posix-storage.md#px-10) |
| <a id="feat-file-tracking"></a>FEAT-file-tracking | Files placed directly on a machine appear in the portal. | [PX-11](requirements/posix-storage.md#px-11) |
| <a id="feat-site-transfer"></a>FEAT-site-transfer | Identifiable data moves between INN and ImageTech. | [PX-12](requirements/posix-storage.md#px-12) |
| <a id="feat-large-uploads"></a>FEAT-large-uploads | Study-sized uploads through the portal. | [PX-15](requirements/posix-storage.md#px-15) |
| <a id="feat-standards"></a>FEAT-standards | Datasets checked against the standard they declare, such as BIDS. | [STD-1](requirements/data-standards.md#std-1), [STD-2](requirements/data-standards.md#std-2) |
| <a id="feat-notifications"></a>FEAT-notifications | Notifications to researchers about their data. | [NT-1](requirements/notifications.md#nt-1) |
| <a id="feat-access-records"></a>FEAT-access-records | Records of who accessed what, readable by administrators and data owners, where any change can be detected. | [AC-9](requirements/access-control.md#ac-9); design: [DS-access-records](design/decision-log.md#ds-access-records) |
| <a id="feat-relationship-access"></a>FEAT-relationship-access | Projects hold access: joining gives it, leaving removes it, and each grant says which project it comes through. | [AC-12](requirements/access-control.md#ac-12); design: [DS-relationship-grants](design/decision-log.md#ds-relationship-grants) |
