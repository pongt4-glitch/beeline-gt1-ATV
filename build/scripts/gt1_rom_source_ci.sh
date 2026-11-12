#!/usr/bin/env bash
# Read-only source integration test. Used by manual GitHub Actions workflows.
# No Android userspace compilation and no hardware interactions.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"

bash -n build/scripts/gt1_full_rom_build.sh
bash -n build/scripts/linux_kernel_module_build.sh
bash -n build/scripts/gt1_rom_source_ci.sh
bash build/scripts/gt1_full_rom_build.sh audit
python3 -B - <<'PY'
from pathlib import Path
import ast
for path in sorted(Path("build/scripts").glob("gt1_*.py")):
    ast.parse(path.read_text())
    print("PYTHON_SYNTAX_PASS", path)
PY

mkdir -p kernel/amlogic hardware/amlogic/kernel-modules
git clone -q --depth 50 --branch lineage-19.1 \
  https://github.com/LineageOS/android_kernel_amlogic_linux-4.9-pie.git \
  kernel/amlogic/linux-4.9-pie
git -C kernel/amlogic/linux-4.9-pie checkout -q \
  ffb8d9d46aac1cde5ee5a1495aa86b62e484ac77

git clone -q --depth 20 --branch lineage-19.1 \
  https://github.com/G12-Development/android_hardware_amlogic_kernel-modules_qca9377.git \
  hardware/amlogic/kernel-modules/qca9377
git -C hardware/amlogic/kernel-modules/qca9377 checkout -q \
  6d051c69d3b8acccc97abdbe0008c764a6901573

git clone -q --depth 20 --branch lineage-19.1 \
  https://github.com/LineageOS/android_hardware_amlogic_kernel-modules_mali-driver.git \
  hardware/amlogic/kernel-modules/mali-driver
git -C hardware/amlogic/kernel-modules/mali-driver checkout -q \
  e436241062014f098c12318033385bdc4e5a2fe8

git clone -q --depth 20 --branch lineage-19.1 \
  https://github.com/LineageOS/android_hardware_amlogic_kernel-modules_media-pie.git \
  hardware/amlogic/kernel-modules/media-pie
git -C hardware/amlogic/kernel-modules/media-pie checkout -q \
  0014f0de13d86f87cae03108b13852ce4e53bb62

git clone -q --depth 20 --branch lineage-19.1 \
  https://github.com/LineageOS/android_hardware_amlogic_kernel-modules_optee-pie.git \
  hardware/amlogic/kernel-modules/optee-pie
git -C hardware/amlogic/kernel-modules/optee-pie checkout -q \
  47248fb86ac2fc5fc0c75589f132a5b73bb312ee

# Re-run exactly the 13 CI Python source edits in disposable clean Linux clones.
python3 -B build/scripts/gt1_export_rom_compat.py --verify \
  --kernel-source kernel/amlogic/linux-4.9-pie \
  --qca-source hardware/amlogic/kernel-modules/qca9377

git -C kernel/amlogic/linux-4.9-pie -c user.name=GT1CI \
  -c user.email=gt1-ci@localhost am \
  "$ROOT"/build/ci-staging/patches/kernel/*.patch \
  "$ROOT"/build/rom-compat-patches/kernel/*.patch

git -C hardware/amlogic/kernel-modules/qca9377 -c user.name=GT1CI \
  -c user.email=gt1-ci@localhost am \
  "$ROOT"/build/ci-staging/patches/qca9377/*.patch \
  "$ROOT"/build/rom-compat-patches/qca9377/*.patch

git -C hardware/amlogic/kernel-modules/mali-driver -c user.name=GT1CI \
  -c user.email=gt1-ci@localhost am \
  "$ROOT"/build/ci-staging/patches/mali/*.patch

for src in kernel/amlogic/linux-4.9-pie \
           hardware/amlogic/kernel-modules/qca9377 \
           hardware/amlogic/kernel-modules/mali-driver \
           hardware/amlogic/kernel-modules/media-pie \
           hardware/amlogic/kernel-modules/optee-pie; do
    test -z "$(git -C "$src" status --porcelain)"
    git -C "$src" log -1 --format='%h %s'
done

test -f hardware/amlogic/kernel-modules/media-pie/drivers/Makefile
test -f hardware/amlogic/kernel-modules/optee-pie/Makefile

cmp "$ROOT/device/amlogic/gt1v30/dts/gt1_v30_2g.dts" \
    "$ROOT/kernel/amlogic/linux-4.9-pie/arch/arm64/boot/dts/amlogic/gt1_v30_2g.dts"

if git ls-files | grep -E '(^device_dump/|^vendor/amlogic/gt1v30/proprietary/|\.img$|\.bin$|\.ko$)'; then
    echo "ERROR: binary/private image unexpectedly committed in public staging" >&2
    exit 1
fi

echo 'PASS: source-equivalent ROM patches apply to pinned Linux kernel, QCA, Mali, media-pie and optee-pie trees'
echo 'NOTE: this does NOT build or test an Android 12L userspace image'
