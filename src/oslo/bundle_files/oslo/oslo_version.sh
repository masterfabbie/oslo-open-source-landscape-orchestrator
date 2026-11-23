#!/bin/sh
# Reports the version of the OSLO operations installed in operations.d and whether their
# files are unchanged (checked against SHA256SUMS of the bundle). Read by OSLO at every
# discovery. Output lines: "oslo_bundle version=<v>" and "oslo_bundle integrity=ok|modified".
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
OPS=$(dirname "$HERE")
if [ -r "$HERE/VERSION" ]; then
    echo "oslo_bundle version=$(head -n 1 "$HERE/VERSION")"
else
    echo "oslo_bundle version=none"
fi
if [ -r "$HERE/SHA256SUMS" ] && (cd "$OPS" && sha256sum -c --quiet --status oslo/SHA256SUMS); then
    echo "oslo_bundle integrity=ok"
else
    echo "oslo_bundle integrity=modified"
fi
