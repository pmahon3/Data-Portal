#!/bin/sh
# Builds the PDF copy beside each doc given (default: the POSIX docs).
# Needs pandoc and xelatex. Rebuild whenever the .md changes.
#   docs/build-pdf.sh [docs/path/doc.md ...]
set -e
cd "$(dirname "$0")/.."
[ $# -gt 0 ] || set -- docs/requirements/posix-storage.md docs/posix/README.md
for md in "$@"; do
  pandoc "$md" -o "${md%.md}.pdf" --pdf-engine=xelatex \
    -f markdown+lists_without_preceding_blankline --lua-filter=docs/pdf-links.lua \
    -V geometry:margin=0.7in -V fontsize=10pt \
    -V monofont=Menlo -V colorlinks -V linkcolor=blue -V urlcolor=blue
  echo "built ${md%.md}.pdf"
done
