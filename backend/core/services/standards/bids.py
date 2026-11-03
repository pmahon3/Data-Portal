"""
Check datasets against BIDS (STD-WHICH, proposed first).

Every file in a dataset must have a name and place the BIDS specification allows (``bids-validator``,
which checks paths against the schema it bundles). Hidden files are left out, as the BIDS validator
does. Sidecar contents, image headers and ``.bidsignore`` need the files themselves, so they're
checked beside the data, later.
"""
from __future__ import annotations

from bids_validator import BIDSValidator

from core.services.standards import Finding

PROBLEM = "not a name or location BIDS allows"

# BIDS datatypes (the specification's "datatype" folders): the kinds of data a policy can name
KINDS = frozenset({
    "anat", "func", "dwi", "fmap", "perf", "meg", "eeg",
    "ieeg", "beh", "pet", "micr", "nirs", "motion", "mrs",
})


class BIDS:
    standard = "BIDS"
    marker = "dataset_description.json"
    kinds = KINDS

    def kind_of(self, path: str) -> str | None:
        """
        Return the datatype folder after sub-*/ or sub-*/ses-*/, for a file inside it; else None.

        Example: "/sub-01/ses-1/anat/x.nii" -> "anat"; "/participants.tsv" -> None
        """
        parts = path.strip("/").split("/")
        if not parts[0].startswith("sub-"):
            return None
        rest = parts[1:]
        if rest and rest[0].startswith("ses-"):
            rest = rest[1:]
        if len(rest) >= 2 and rest[0] in KINDS:
            return rest[0]
        return None

    def check(self, paths: list[str]) -> list[Finding]:
        """Return a finding for each path BIDS doesn't allow, leaving out hidden files."""
        validator = BIDSValidator()
        findings = []
        for path in paths:
            hidden = any(part.startswith(".") for part in path.split("/"))
            if not hidden and not validator.is_bids(path):
                findings.append(Finding(path, PROBLEM))
        return findings
