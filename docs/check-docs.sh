#!/bin/sh
# Prose and structure checks for the user guide, from pinned Docker images so nothing is installed.
# Vale applies the house style in .vale/styles/Portal (errors fail; warnings and suggestions inform);
# markdownlint checks headings, lists and links (.markdownlint-cli2.yaml). Local links and anchors are
# also checked by backend/tests/test_docs_links.py.
set -u
cd "$(dirname "$0")/.."
status=0
docker run --rm -v "$PWD:/repo" -w /repo jdkato/vale:v3.12.0 --minAlertLevel=warning docs/user-guide || status=1
docker run --rm -v "$PWD:/workdir" davidanson/markdownlint-cli2:v0.18.1 || status=1
[ $status -eq 0 ] && echo "docs checks passed"
exit $status
