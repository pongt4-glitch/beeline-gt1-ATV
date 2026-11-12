#!/usr/bin/env bash
# Beelink GT1 Classic — source-equivalent LineageOS 19.1 build (Linux x86_64).
# No flashing, USB burning, eMMC writes or bootloader changes are implemented.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ACTION="${1:-audit}"
LINEAGE_ROOT="${GT1_LINEAGE_ROOT:-${HOME}/android/lineage-19.1}"
PRIVATE_VENDOR_ROOT="${GT1_PRIVATE_VENDOR_ROOT:-}"
JOBS="${GT1_BUILD_JOBS:-2}"
MIN_FREE_GIB="${GT1_MIN_FREE_GIB:-400}"
MIN_RAM_GIB="${GT1_MIN_RAM_GIB:-32}"

KERNEL_PIN="ffb8d9d46aac1cde5ee5a1495aa86b62e484ac77"
QCA_PIN="6d051c69d3b8acccc97abdbe0008c764a6901573"
MALI_PIN="e436241062014f098c12318033385bdc4e5a2fe8"

case "$ACTION" in
  audit|check-host|sync|patch|overlay|kernel|rom|verify|all) ;;
  *)
    echo "Usage: $0 {audit|check-host|sync|patch|overlay|kernel|rom|verify|all}" >&2
    exit 2
    ;;
esac

say() { printf '[gt1-rom] %s\n' "$*"; }
die() { printf '[gt1-rom][ERROR] %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "Missing dependency: $1"; }

audit() {
  need python3
  python3 "$STAGING_ROOT/build/scripts/gt1_manifest_audit.py" \
    "$STAGING_ROOT/build/manifests/gt1v30.xml"
  python3 "$STAGING_ROOT/build/scripts/gt1_rom_compat_manifest_audit.py" \
    "$STAGING_ROOT/build/rom-compat-patches/manifest.json" "$STAGING_ROOT"
  [[ -f "$STAGING_ROOT/device/amlogic/gt1v30/dts/gt1_v30_2g.dts" ]] \
    || die "Missing GT1 device DTS in public staging"
  if [[ -n "$PRIVATE_VENDOR_ROOT" ]]; then
    python3 "$STAGING_ROOT/build/scripts/gt1_validate_vendor_blobs.py" \
      --manifest "$STAGING_ROOT/device/amlogic/gt1v30/proprietary-files.txt" \
      --vendor-root "$PRIVATE_VENDOR_ROOT/proprietary"
  else
    say "Private vendor overlay not supplied; proprietary blob check skipped"
  fi
  say "Public source/manifest audit PASS"
}

host_check() {
  [[ "$(uname -s)" == "Linux" ]] || die "Android 12L ROM build needs Linux x86_64 (host is $(uname -s))"
  [[ "$(uname -m)" == "x86_64" ]] || die "Android 12L host prebuilts need x86_64"
  local probe="$LINEAGE_ROOT"
  while [[ ! -d "$probe" ]]; do probe="$(dirname "$probe")"; done
  local free_kib free_gib ram_kib ram_gib
  free_kib="$(df -Pk "$probe" | awk 'NR==2 {print $4}')"
  free_gib="$(( free_kib / 1024 / 1024 ))"
  [[ "$free_gib" -ge "$MIN_FREE_GIB" ]] \
    || die "Only ${free_gib} GiB free in $probe, require ${MIN_FREE_GIB} GiB"
  ram_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
  ram_gib="$(( ram_kib / 1024 / 1024 ))"
  [[ "$ram_gib" -ge "$MIN_RAM_GIB" ]] \
    || die "Only ${ram_gib} GiB RAM; require ${MIN_RAM_GIB} GiB before starting"
  if [[ -d "$LINEAGE_ROOT" ]]; then
    local test_dir="$LINEAGE_ROOT/.gt1-case-probe-$$"
    mkdir "$test_dir"
    trap 'rm -rf "$test_dir"' RETURN
    printf A > "$test_dir/A"
    printf a > "$test_dir/a"
    [[ "$(cat "$test_dir/A")" == A && "$(cat "$test_dir/a")" == a ]] \
      || die "Build checkout is on a case-insensitive filesystem"
    rm -rf "$test_dir"
    trap - RETURN
  fi
  need git
  need python3
  need rsync
  need repo
  say "Linux x86_64 host check PASS; free ${free_gib} GiB; RAM ${ram_gib} GiB"
}

# Only changes source checkouts under LINEAGE_ROOT. Exits if source is dirty,
# a different upstream revision was checked out, or a patch set is ambiguous.
apply_patches() {
  local name="$1" tree="$2" pinned="$3" final_subject="$4"
  shift 4
  local -a patches=("$@")
  [[ -d "$tree" ]] || die "$name source checkout missing: $tree"
  [[ -z "$(git -C "$tree" status --porcelain)" ]] \
    || die "$name checkout has uncommitted changes — refusing to alter user work"
  local current
  current="$(git -C "$tree" rev-parse HEAD)"
  if [[ "$current" == "$pinned" ]]; then
    [[ "${#patches[@]}" -gt 0 ]] || die "Missing patch list for $name"
    say "Applying ${#patches[@]} reviewed patches: $name"
    git -C "$tree" -c user.name="GT1 Build Integration" \
      -c user.email="gt1-integrator@localhost" am "${patches[@]}"
  elif git -C "$tree" merge-base --is-ancestor "$pinned" "$current" && \
       [[ "$(git -C "$tree" log -1 --format=%s)" == "$final_subject" ]]; then
    say "$name patched series appears already applied (HEAD=$current)"
  else
    die "$name at unexpected HEAD=$current (pinned=$pinned); do not force-sync or reset"
  fi
}

patch_sources() {
  local root="$LINEAGE_ROOT"
  [[ -f "$root/build/envsetup.sh" ]] || die "Full AOSP source missing: $root/build/envsetup.sh"
  local -a kernel=("$STAGING_ROOT"/build/ci-staging/patches/kernel/*.patch
                   "$STAGING_ROOT"/build/rom-compat-patches/kernel/*.patch)
  local -a qca=("$STAGING_ROOT"/build/ci-staging/patches/qca9377/*.patch
                "$STAGING_ROOT"/build/rom-compat-patches/qca9377/*.patch)
  local -a mali=("$STAGING_ROOT"/build/ci-staging/patches/mali/*.patch)
  [[ "${#kernel[@]}" == 7 && "${#qca[@]}" == 3 && "${#mali[@]}" == 1 ]] \
    || die "Expected kernel 7, QCA 3 and Mali 1 reviewed patches"
  apply_patches kernel "$root/kernel/amlogic/linux-4.9-pie" "$KERNEL_PIN" \
    "fix(kernel): mirror CI GCC9 and Amlogic compatibility" "${kernel[@]}"
  apply_patches qca9377 "$root/hardware/amlogic/kernel-modules/qca9377" "$QCA_PIN" \
    "fix(qca9377): mirror CI SME and SAP compatibility" "${qca[@]}"
  apply_patches mali "$root/hardware/amlogic/kernel-modules/mali-driver" "$MALI_PIN" \
    "midgard: Default KERNEL_ARCH to TARGET_KERNEL_ARCH for Kati target resolution" "${mali[@]}"
  say "Pinned kernel, QCA and Mali patches applied; no original upstream source overwritten"
}

overlay_device_vendor() {
  [[ -d "$LINEAGE_ROOT/device/amlogic/gx-common" ]] \
    || die "Missing gx-common device tree; run sync first"
  [[ -n "$PRIVATE_VENDOR_ROOT" && -f "$PRIVATE_VENDOR_ROOT/gt1v30-vendor.mk" ]] \
    || die "GT1_PRIVATE_VENDOR_ROOT must be the private vendor/amlogic/gt1v30 directory"
  audit
  mkdir -p "$LINEAGE_ROOT/device/amlogic/gt1v30" "$LINEAGE_ROOT/vendor/amlogic/gt1v30"
  rsync -a --exclude='.git' --exclude='*.pyc' \
    "$STAGING_ROOT/device/amlogic/gt1v30/" "$LINEAGE_ROOT/device/amlogic/gt1v30/"
  rsync -a --exclude='.git' --exclude='*.pyc' \
    "$PRIVATE_VENDOR_ROOT/" "$LINEAGE_ROOT/vendor/amlogic/gt1v30/"
  cmp "$STAGING_ROOT/device/amlogic/gt1v30/dts/gt1_v30_2g.dts" \
    "$LINEAGE_ROOT/kernel/amlogic/linux-4.9-pie/arch/arm64/boot/dts/amlogic/gt1_v30_2g.dts" \
    || die "Device DTS differs from pinned patched kernel DTS"
  [[ -f "$LINEAGE_ROOT/vendor/amlogic/gx-common/gx-common-vendor.mk" ]] \
    || die "Missing common Amlogic proprietary vendor makefile"
  if find "$LINEAGE_ROOT/vendor/amlogic/gt1v30" -name '*.ko' -print -quit | grep -q .; then
    die "Stale prebuilt kernel module found in proprietary vendor overlay"
  fi
  say "Device and vendor overlays PASS; no --delete was used"
}

source_setup() {
  [[ -f "$LINEAGE_ROOT/build/envsetup.sh" ]] || die "Missing LineageOS source"
  cd "$LINEAGE_ROOT"
  set +u
  # shellcheck source=/dev/null
  source build/envsetup.sh
  lunch lineage_gt1v30-userdebug
  set -u
}

sync_source() {
  host_check
  [[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "Invalid GT1_BUILD_JOBS=$JOBS"
  mkdir -p "$LINEAGE_ROOT/.repo/local_manifests"
  local manifest="$LINEAGE_ROOT/.repo/local_manifests/gt1v30.xml"
  if [[ -f "$manifest" ]] && ! cmp -s "$manifest" "$STAGING_ROOT/build/manifests/gt1v30.xml"; then
    die "Existing local manifest differs; will not overwrite it"
  fi
  cp "$STAGING_ROOT/build/manifests/gt1v30.xml" "$manifest"
  cd "$LINEAGE_ROOT"
  if [[ ! -f ".repo/manifests/default.xml" ]]; then
    repo init -u https://github.com/LineageOS/android.git -b lineage-19.1 --git-lfs --no-clone-bundle
  fi
  repo sync -c -j"$JOBS" --no-clone-bundle --no-tags
  say "Full LineageOS 19.1 source sync PASS"
}

build_rom() {
  local target="$1"
  host_check
  source_setup
  [[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "Invalid jobs count"
  if [[ "$target" == kernel ]]; then
    m bootimage dtboimage -j"$JOBS"
    python3 "$STAGING_ROOT/build/scripts/gt1_verify_image_sizes.py" \
      "$LINEAGE_ROOT/out/target/product/gt1v30" boot.img dtbo.img
  else
    m bacon -j"$JOBS"
    python3 "$STAGING_ROOT/build/scripts/gt1_verify_image_sizes.py" \
      "$LINEAGE_ROOT/out/target/product/gt1v30"
  fi
  say "$target build completed — artifacts are local only, never flashed"
}

audit
case "$ACTION" in
  audit) ;;
  check-host) host_check ;;
  sync) sync_source ;;
  patch) host_check; patch_sources ;;
  overlay) host_check; overlay_device_vendor ;;
  kernel) build_rom kernel ;;
  rom) build_rom rom ;;
  verify) python3 "$STAGING_ROOT/build/scripts/gt1_verify_image_sizes.py" \
            "$LINEAGE_ROOT/out/target/product/gt1v30" ;;
  all)
    sync_source
    patch_sources
    overlay_device_vendor
    build_rom rom
    ;;
esac
