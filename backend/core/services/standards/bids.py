"""
BIDS (E-STD, proposed first): every file in a dataset must have a name and place the BIDS
specification allows (``bids-validator``, which checks paths against the schema it bundles).
Hidden files are left out, as the BIDS validator does. Sidecar contents, image headers and
``.bidsignore`` need the files themselves, so they're checked beside the data, later.
"""
from bids_validator import BIDSValidator

from core.services.standards import Finding

PROBLEM = "not a name or location BIDS allows"

# BIDS datatypes (the specification's "datatype" folders): the kinds of data a policy can name
KINDS = frozenset({"anat", "func", "dwi", "fmap", "perf", "meg", "eeg", "ieeg", "beh", "pet", "micr",
                   "nirs", "motion", "mrs"})


class BIDS:
    standard = "BIDS"
    marker = "dataset_description.json"
    kinds = KINDS

    def kind_of(self, path: str) -> str | None:
        """The datatype folder after sub-*/ or sub-*/ses-*/, for a file inside it; else None."""
        parts = path.strip("/").split("/")
        if not parts[0].startswith("sub-"):
            return None
        rest = parts[1:]
        if rest and rest[0].startswith("ses-"):
            rest = rest[1:]
        return rest[0] if len(rest) >= 2 and rest[0] in KINDS else None

    def check(self, paths: list[str]) -> list[Finding]:
        validator = BIDSValidator()
        return [Finding(p, PROBLEM) for p in paths
                if not any(part.startswith(".") for part in p.split("/")) and not validator.is_bids(p)]
