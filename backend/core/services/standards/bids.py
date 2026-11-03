"""
BIDS (E-STD, proposed first): every file in a dataset must have a name and place the BIDS
specification allows (``bids-validator``, which checks paths against the schema it bundles).
Hidden files are left out, as the BIDS validator does. Sidecar contents, image headers and
``.bidsignore`` need the files themselves, so they're checked beside the data, later.
"""
from bids_validator import BIDSValidator

from core.services.standards import Finding

PROBLEM = "not a name or location BIDS allows"


class BIDS:
    standard = "BIDS"
    marker = "dataset_description.json"

    def check(self, paths: list[str]) -> list[Finding]:
        validator = BIDSValidator()
        return [Finding(p, PROBLEM) for p in paths
                if not any(part.startswith(".") for part in p.split("/")) and not validator.is_bids(p)]
