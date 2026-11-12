#!/usr/bin/env bash
# Generate and verify both Priority-1 patches without writing to actual devices.
# Run this from the CI staging repository's root, or use any cwd.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/../.." && pwd)"
cd "$REPO"

# Homebrew Python may not auto-load the system CA bundle on macOS.
# Use the macOS-trusted CA file; never disable certificate verification.
if [[ "$(uname -s)" == "Darwin" && -z "${SSL_CERT_FILE:-}" && -f /etc/ssl/cert.pem ]]; then
  export SSL_CERT_FILE=/etc/ssl/cert.pem
fi

EXPECTED_BASE="4ca2c8e79251ca450134fc88cc783a43b59b3737"
if ! git merge-base --is-ancestor "$EXPECTED_BASE" HEAD; then
  echo "STOP: expected baseline $EXPECTED_BASE is not an ancestor of HEAD" >&2
  exit 2
fi

OUT_DIR="$REPO/build/ci-staging/patches/kernel"
P1="$OUT_DIR/0004-kernel-harden-string-operations-batch-1.patch"
P2="$OUT_DIR/0005-kernel-harden-string-operations-batch-2.patch"

# Re-generate into a temporary directory, and compare exact bytes.
# Never overwrite tracked or staged patches.
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/gt1-priority1.XXXXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
python3 "$HERE/gt1_priority1_batch1.py" --output "$TMP_ROOT/0004.patch"
python3 "$HERE/gt1_priority1_batch2.py" --output "$TMP_ROOT/0005.patch"
cmp "$TMP_ROOT/0004.patch" "$P1"
cmp "$TMP_ROOT/0005.patch" "$P2"
echo "PASS: generated patch bytes match staged patch files"

# Validate git-am applies both new patches after exactly the existing three.

git clone --depth 50 --branch lineage-19.1 \
  https://github.com/LineageOS/android_kernel_amlogic_linux-4.9-pie.git \
  "$TMP_ROOT/kernel"
git -C "$TMP_ROOT/kernel" checkout --detach ffb8d9d4

git -C "$TMP_ROOT/kernel" -c user.name="GT1 Patch Validator" \
  -c user.email="gt1-validator@localhost" \
  am "$OUT_DIR"/0001-*.patch "$OUT_DIR"/0002-*.patch \
     "$OUT_DIR"/0003-*.patch "$P1" "$P2"

git -C "$TMP_ROOT/kernel" log -5 --oneline
git -C "$TMP_ROOT/kernel" show --check --oneline HEAD
git -C "$TMP_ROOT/kernel" show --check --oneline HEAD^

echo "PASS: Both patches apply cleanly to pinned upstream after existing patches."
echo "NOTE: This does NOT verify compilation or runtime safety."
echo "NOTE: Nothing was committed or pushed to the staging repository."
echo "Next: inspect .patch files, commit on a feature branch, then dispatch CI."
