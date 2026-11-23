#!/bin/sh
# Installs the OSLO operations into operations.d of the host agent. Runs as root.
#
#   oslo_update.sh
#       Downloads the current bundle from the OSLO server named in oslo.cfg (HTTPS only),
#       checks its signature with bundle_key.pem and installs it.
#   oslo_update.sh --local <payload.tar.gz> <payload.sig> <bundle_key.pem> <operations.d>
#       Installs a bundle that is already on the host (used by install.sh of the bootstrap
#       package).
#
# Only files of OSLO are touched: oslo_*.conf in operations.d and the directory oslo/;
# bundle_key.pem and oslo.cfg stay. Files are replaced by renaming, so a running script
# keeps its old copy.
set -eu
umask 022
PATH=/usr/bin:/bin:/usr/sbin:/sbin

fail() {
    echo "[ERROR]: $*"
    exit 1
}

for tool in openssl tar sha256sum mktemp; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is missing"
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if [ "${1:-}" = "--local" ]; then
    [ $# -eq 5 ] || fail "usage: $0 --local <payload.tar.gz> <payload.sig> <bundle_key.pem> <operations.d>"
    cp "$2" "$tmp/payload.tar.gz"
    cp "$3" "$tmp/payload.sig"
    KEY=$4
    OPS=$5
else
    HERE=$(cd "$(dirname "$0")" && pwd)
    OPS=$(dirname "$HERE")
    KEY=$HERE/bundle_key.pem
    CFG=$HERE/oslo.cfg
    [ -r "$CFG" ] || fail "$CFG is missing; install the bootstrap package first"
    URL=$(sed -n 's/^OSLO_URL=//p' "$CFG" | head -n 1)
    CA=$(sed -n 's/^OSLO_CA=//p' "$CFG" | head -n 1)
    case "$URL" in
        https://*) ;;
        *) fail "OSLO_URL in $CFG must start with https://" ;;
    esac
    command -v curl >/dev/null 2>&1 || fail "curl is missing"
    for name in payload.tar.gz payload.sig; do
        if [ -n "$CA" ]; then
            curl -fsS --proto =https --max-time 120 --cacert "$CA" -o "$tmp/$name" "$URL/bundle/$name" \
                || fail "download of $URL/bundle/$name failed"
        else
            curl -fsS --proto =https --max-time 120 -o "$tmp/$name" "$URL/bundle/$name" \
                || fail "download of $URL/bundle/$name failed"
        fi
    done
fi
[ -r "$KEY" ] || fail "$KEY is missing; install the bootstrap package first"

openssl pkeyutl -verify -pubin -inkey "$KEY" -rawin -in "$tmp/payload.tar.gz" \
    -sigfile "$tmp/payload.sig" >/dev/null 2>&1 || fail "the signature of the bundle is not valid"

# Only regular files and directories, only names of OSLO, no "..".
bad=$(tar -tvzf "$tmp/payload.tar.gz" | cut -c1 | grep -v '^[-d]$' || true)
[ -z "$bad" ] || fail "the bundle contains links or special files"
bad=$(tar -tzf "$tmp/payload.tar.gz" | grep -Ev '^(oslo_[A-Za-z0-9_-]+\.conf|oslo/|oslo/[A-Za-z0-9_.-]+)$' || true)
[ -z "$bad" ] || fail "the bundle contains unexpected files: $bad"
if tar -tzf "$tmp/payload.tar.gz" | grep -q '\.\.'; then
    fail "the bundle contains unexpected file names"
fi

mkdir "$tmp/new"
tar -xzf "$tmp/payload.tar.gz" -C "$tmp/new" --no-same-owner
(cd "$tmp/new" && sha256sum -c --quiet --status oslo/SHA256SUMS) \
    || fail "the files do not match SHA256SUMS of the bundle"
version=$(head -n 1 "$tmp/new/oslo/VERSION")

mkdir -p "$OPS/oslo"
# Copy next to the target, then rename: atomic, and running scripts keep their copy.
for file in "$tmp/new"/oslo_*.conf "$tmp/new"/oslo/*; do
    name=${file#"$tmp/new/"}
    cp "$file" "$OPS/$name.new"
    case "$name" in
        *.sh) chmod 755 "$OPS/$name.new" ;;
        *) chmod 644 "$OPS/$name.new" ;;
    esac
done
for old in "$OPS"/oslo_*.conf "$OPS"/oslo/*; do
    [ -e "$old" ] || continue
    name=${old#"$OPS/"}
    case "$name" in
        *.new | oslo/bundle_key.pem | oslo/oslo.cfg) continue ;;
    esac
    [ -e "$tmp/new/$name" ] || rm -f "$old"
done
for file in "$OPS"/oslo_*.conf.new "$OPS"/oslo/*.new; do
    [ -e "$file" ] || continue
    mv -f "$file" "${file%.new}"
done
echo "oslo_bundle installed=$version"
