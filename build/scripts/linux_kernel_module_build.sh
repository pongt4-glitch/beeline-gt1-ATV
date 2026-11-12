#!/usr/bin/env bash
# ==============================================================================
# Beelink GT1 Classic (GT-T_V30_20160831) — Linux Kernel 4.9.113 & Modules Build
# Target Host: Ubuntu 22.04 x86-64 (GitHub Actions) or Ubuntu 22.04 ARM64 (Lima)
# Toolchain:   Linaro GCC 7.5.0-2019.12 (x86_64 -> aarch64-linux-gnu)
# Budget:      0 THB | Strict Verification (No fake outputs, no global -Wno-error)
# ==============================================================================
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KERNEL_SRC="${WORKSPACE_ROOT}/kernel/amlogic/linux-4.9-pie"
MALI_ROOT="${WORKSPACE_ROOT}/hardware/amlogic/kernel-modules/mali-driver"
MALI_REL="midgard/r28p0/kernel/drivers/gpu/arm/midgard"
QCA_ROOT="${WORKSPACE_ROOT}/hardware/amlogic/kernel-modules/qca9377"
QCA_REL="AIO/drivers/qcacld-new"
OUT_ROOT="${WORKSPACE_ROOT}/out/linux-kernel-build"
KERNEL_OUT="${OUT_ROOT}/KERNEL_OBJ"
MODULES_STAGE="${OUT_ROOT}/modules_staging"
ARTIFACTS_DIR="${OUT_ROOT}/artifacts"
LOG_DIR="${OUT_ROOT}/logs"

JOBS="${JOBS:-2}"
CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"
HOSTCC_BIN="${HOSTCC_BIN:-gcc}"
MIN_FREE_KB="${MIN_FREE_KB:-2097152}" # Stop before disk full (< 2 GiB free)

mkdir -p "${KERNEL_OUT}" "${MODULES_STAGE}/mali" "${MODULES_STAGE}/qca9377" "${ARTIFACTS_DIR}" "${LOG_DIR}"

check_disk_space() {
  local stage_name="$1"
  local avail_kb
  avail_kb="$(df -Pk "${WORKSPACE_ROOT}" | awk 'NR==2 {print $4}')"
  echo "[DISK GUARD] Stage '${stage_name}': ${avail_kb} KiB free (minimum required: ${MIN_FREE_KB} KiB)" | tee -a "${LOG_DIR}/disk_usage.log"
  if [ "${avail_kb}" -lt "${MIN_FREE_KB}" ]; then
    echo "FATAL: Disk free space (${avail_kb} KiB) dropped below safety threshold (${MIN_FREE_KB} KiB) at stage '${stage_name}'. Stopping cleanly before disk full!" >&2
    exit 28
  fi
}

echo "=== [STEP 1] Runner & Disk Preflight ===" | tee "${LOG_DIR}/01_preflight.log"
uname -a | tee -a "${LOG_DIR}/01_preflight.log"
df -h "${WORKSPACE_ROOT}" | tee -a "${LOG_DIR}/01_preflight.log"
free -h 2>/dev/null | tee -a "${LOG_DIR}/01_preflight.log" || true
check_disk_space "01_preflight"

echo "=== [STEP 2] Source / License / Security Validation ===" | tee "${LOG_DIR}/02_security_validation.log"
if find "${WORKSPACE_ROOT}" -maxdepth 3 \( -path "*/device_dump/*" -o -path "*/vendor/amlogic/gt1v30/proprietary/*" -o -name "*.pem" -o -name "*.pk8" \) 2>/dev/null | grep -q .; then
  if [ "${GITHUB_ACTIONS:-false}" = "true" ]; then
    echo "FATAL: Prohibited partition dump, proprietary blob, or private key detected on CI runner!" | tee -a "${LOG_DIR}/02_security_validation.log"
    exit 1
  else
    echo "INFO: Local workspace detected; build script will only touch open-source trees." | tee -a "${LOG_DIR}/02_security_validation.log"
  fi
fi

echo "=== [STEP 3] Verify Source Trees & Commits ===" | tee "${LOG_DIR}/03_source_commits.log"
for repo_dir in "${KERNEL_SRC}" "${MALI_ROOT}" "${QCA_ROOT}"; do
  if [ ! -d "${repo_dir}" ]; then
    echo "FATAL: Missing source directory ${repo_dir}" | tee -a "${LOG_DIR}/03_source_commits.log"
    exit 1
  fi
  echo "Repo ${repo_dir}: $(git -C "${repo_dir}" rev-parse HEAD) ($(git -C "${repo_dir}" log -1 --pretty=%s))" | tee -a "${LOG_DIR}/03_source_commits.log"
done

echo "=== [STEP 4] Toolchain Architecture & Binary Verification ===" | tee "${LOG_DIR}/04_toolchain_verification.log"
GCC_PATH="$(command -v "${CROSS_COMPILE}gcc")"
LD_PATH="$(command -v "${CROSS_COMPILE}ld")"
OBJCOPY_PATH="$(command -v "${CROSS_COMPILE}objcopy")"
READELF_PATH="$(command -v "${CROSS_COMPILE}readelf")"
file "${GCC_PATH}" "${LD_PATH}" "${OBJCOPY_PATH}" "${READELF_PATH}" | tee -a "${LOG_DIR}/04_toolchain_verification.log"
"${CROSS_COMPILE}gcc" --version | tee -a "${LOG_DIR}/04_toolchain_verification.log"
"${CROSS_COMPILE}ld" --version | tee -a "${LOG_DIR}/04_toolchain_verification.log"
"${CROSS_COMPILE}objcopy" --version | head -n 2 | tee -a "${LOG_DIR}/04_toolchain_verification.log"
"${CROSS_COMPILE}readelf" --version | head -n 2 | tee -a "${LOG_DIR}/04_toolchain_verification.log"
"${HOSTCC_BIN}" --version | head -n 2 | tee -a "${LOG_DIR}/04_toolchain_verification.log"
make --version | head -n 2 | tee -a "${LOG_DIR}/04_toolchain_verification.log"
flex --version | head -n 2 | tee -a "${LOG_DIR}/04_toolchain_verification.log"
bison --version | head -n 2 | tee -a "${LOG_DIR}/04_toolchain_verification.log"

echo "=== [STEP 5] Kernel Defconfig (meson64_defconfig) ===" | tee "${LOG_DIR}/05_kernel_defconfig.log"
make -C "${KERNEL_SRC}" O="${KERNEL_OUT}" \
  ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE}" \
  HOSTCC="${HOSTCC_BIN}" HOSTCFLAGS="-O2 -fcommon" \
  meson64_defconfig 2>&1 | tee -a "${LOG_DIR}/05_kernel_defconfig.log"
sha256sum "${KERNEL_OUT}/.config" | tee -a "${LOG_DIR}/05_kernel_defconfig.log"
check_disk_space "05_kernel_defconfig"

echo "=== [STEP 6] Kernel Host Tools & Device Tree Build (scripts, prepare, dtbs) ===" | tee "${LOG_DIR}/06_host_tools_dtbs.log"
make -C "${KERNEL_SRC}" O="${KERNEL_OUT}" \
  ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE}" \
  HOSTCC="${HOSTCC_BIN}" HOSTCFLAGS="-O2 -fcommon" \
  -j"${JOBS}" scripts prepare dtbs 2>&1 | tee -a "${LOG_DIR}/06_host_tools_dtbs.log"
test -x "${KERNEL_OUT}/scripts/mod/modpost"
test -x "${KERNEL_OUT}/scripts/dtc/dtc"
test -f "${KERNEL_OUT}/arch/arm64/boot/dts/amlogic/gt1_v30_2g.dtb"
check_disk_space "06_host_tools_dtbs"

echo "=== [STEP 7 & STEP 8] Full Kernel Compilation & Link vmlinux ===" | tee "${LOG_DIR}/07_08_kernel_vmlinux.log"
make -C "${KERNEL_SRC}" O="${KERNEL_OUT}" \
  ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE}" \
  HOSTCC="${HOSTCC_BIN}" HOSTCFLAGS="-O2 -fcommon" \
  CONFIG_DEBUG_SECTION_MISMATCH=y \
  CONFIG_SECTION_MISMATCH_WARN_ONLY=y \
  -j"${JOBS}" vmlinux modules 2>&1 | tee -a "${LOG_DIR}/07_08_kernel_vmlinux.log"
test -f "${KERNEL_OUT}/vmlinux"
test -f "${KERNEL_OUT}/Module.symvers"
check_disk_space "08_vmlinux"

echo "=== [STEP 9] Generate Image.gz ===" | tee "${LOG_DIR}/09_image_gz.log"
make -C "${KERNEL_SRC}" O="${KERNEL_OUT}" \
  ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE}" \
  HOSTCC="${HOSTCC_BIN}" HOSTCFLAGS="-O2 -fcommon" \
  -j"${JOBS}" Image.gz 2>&1 | tee -a "${LOG_DIR}/09_image_gz.log"
test -f "${KERNEL_OUT}/arch/arm64/boot/Image.gz"
ls -lh "${KERNEL_OUT}/arch/arm64/boot/Image.gz" | tee -a "${LOG_DIR}/09_image_gz.log"
check_disk_space "09_image_gz"

echo "=== [STEP 10] Build Mali Midgard r28p0 (mali_kbase.ko -> mali.ko) ===" | tee "${LOG_DIR}/10_mali_module.log"
rm -rf "${MODULES_STAGE}/mali" && mkdir -p "${MODULES_STAGE}/mali"
cp -R "${MALI_ROOT}/"* "${MODULES_STAGE}/mali/"
MALI_BUILD_DIR="${MODULES_STAGE}/mali/${MALI_REL}"
MALI_CFLAGS="-Wno-pointer-sign -I${MALI_BUILD_DIR}/backend/gpu -I${MALI_BUILD_DIR}/platform/devicetree -I${MALI_BUILD_DIR}/ipa -I${MALI_BUILD_DIR} -I${MODULES_STAGE}/mali/dvalin/kernel/include -DCONFIG_MALI_PLATFORM_DEVICETREE -DCONFIG_MALI_MIDGARD_DVFS -DCONFIG_MALI_BACKEND=gpu"
make -C "${KERNEL_OUT}" \
  M="${MALI_BUILD_DIR}" \
  ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE}" \
  HOSTCC="${HOSTCC_BIN}" HOSTCFLAGS="-O2 -fcommon" \
  EXTRA_CFLAGS="${MALI_CFLAGS}" \
  CONFIG_MALI_MIDGARD=m CONFIG_MALI_PLATFORM_DEVICETREE=y CONFIG_MALI_MIDGARD_DVFS=y CONFIG_MALI_BACKEND=gpu \
  -j"${JOBS}" modules 2>&1 | tee -a "${LOG_DIR}/10_mali_module.log"
test -f "${MALI_BUILD_DIR}/mali_kbase.ko"
"${CROSS_COMPILE}strip" --strip-unneeded "${MALI_BUILD_DIR}/mali_kbase.ko"
cp "${MALI_BUILD_DIR}/mali_kbase.ko" "${ARTIFACTS_DIR}/mali.ko"
check_disk_space "10_mali_module"

echo "=== [STEP 11] Build Qualcomm QCA9377 (wlan.ko -> qca9377.ko) ===" | tee "${LOG_DIR}/11_qca9377_module.log"
rm -rf "${MODULES_STAGE}/qca9377" && mkdir -p "${MODULES_STAGE}/qca9377"
cp -R "${QCA_ROOT}/"* "${MODULES_STAGE}/qca9377/"
QCA_BUILD_DIR="${MODULES_STAGE}/qca9377/${QCA_REL}"
make -C "${KERNEL_OUT}" \
  M="${QCA_BUILD_DIR}" \
  ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE}" \
  HOSTCC="${HOSTCC_BIN}" HOSTCFLAGS="-O2 -fcommon" \
  WLAN_ROOT="${QCA_BUILD_DIR}" MODNAME=wlan \
  CONFIG_QCA_WIFI_ISOC=0 CONFIG_QCA_WIFI_2_0=1 CONFIG_QCA_CLD_WLAN=m \
  WLAN_OPEN_SOURCE=1 CONFIG_CLD_HL_SDIO_CORE=y CONFIG_LINUX_QCMBR=y CONFIG_NON_QC_PLATFORM=y \
  -j"${JOBS}" modules 2>&1 | tee -a "${LOG_DIR}/11_qca9377_module.log"
test -f "${QCA_BUILD_DIR}/wlan.ko"
"${CROSS_COMPILE}strip" --strip-unneeded "${QCA_BUILD_DIR}/wlan.ko"
cp "${QCA_BUILD_DIR}/wlan.ko" "${ARTIFACTS_DIR}/qca9377.ko"
check_disk_space "11_qca9377_module"

echo "=== [STEP 12 & STEP 13] modpost, Module.symvers, ELF64, vermagic & Unresolved Symbols Validation ===" | tee "${LOG_DIR}/12_13_module_validation.log"
cp "${KERNEL_OUT}/arch/arm64/boot/Image.gz" "${ARTIFACTS_DIR}/Image.gz"
cp "${KERNEL_OUT}/arch/arm64/boot/dts/amlogic/gt1_v30_2g.dtb" "${ARTIFACTS_DIR}/gt1_v30_2g.dtb"
cp "${KERNEL_OUT}/Module.symvers" "${ARTIFACTS_DIR}/Module.symvers"
cp "${KERNEL_OUT}/.config" "${ARTIFACTS_DIR}/kernel.config"

"${CROSS_COMPILE}readelf" -h "${KERNEL_OUT}/vmlinux" | tee -a "${LOG_DIR}/12_13_module_validation.log"

UNRESOLVED_COUNT=0
for ko in "${ARTIFACTS_DIR}/mali.ko" "${ARTIFACTS_DIR}/qca9377.ko"; do
  echo "--- Inspecting ${ko} ---" | tee -a "${LOG_DIR}/12_13_module_validation.log"
  file "${ko}" | grep "ELF 64-bit LSB relocatable, ARM aarch64" | tee -a "${LOG_DIR}/12_13_module_validation.log"
  "${CROSS_COMPILE}readelf" -h "${ko}" | tee -a "${LOG_DIR}/12_13_module_validation.log"
  modinfo "${ko}" | tee -a "${LOG_DIR}/12_13_module_validation.log"
  while read -r sym; do
    if [ -n "${sym}" ]; then
      if ! grep -q -w "${sym}" "${KERNEL_OUT}/Module.symvers" && ! "${CROSS_COMPILE}nm" "${KERNEL_OUT}/vmlinux" | grep -q -w "${sym}"; then
        echo "ERROR: Unresolved symbol '${sym}' in ${ko}!" | tee -a "${LOG_DIR}/12_13_module_validation.log"
        UNRESOLVED_COUNT=$((UNRESOLVED_COUNT + 1))
      fi
    fi
  done < <("${CROSS_COMPILE}nm" -u "${ko}" | awk '{print $2}')
done

if [ "${UNRESOLVED_COUNT}" -gt 0 ]; then
  echo "FATAL: ${UNRESOLVED_COUNT} unresolved symbols detected across built modules!" | tee -a "${LOG_DIR}/12_13_module_validation.log"
  exit 1
fi
echo "PASS: 0 unresolved symbols against vmlinux / Module.symvers." | tee -a "${LOG_DIR}/12_13_module_validation.log"

echo "=== [STEP 14] SHA-256 Checksums & Artifact Manifest ===" | tee "${LOG_DIR}/14_sha256.log"
sha256sum "${ARTIFACTS_DIR}/Image.gz" \
          "${ARTIFACTS_DIR}/gt1_v30_2g.dtb" \
          "${ARTIFACTS_DIR}/mali.ko" \
          "${ARTIFACTS_DIR}/qca9377.ko" \
          "${ARTIFACTS_DIR}/Module.symvers" \
          "${ARTIFACTS_DIR}/kernel.config" | tee "${ARTIFACTS_DIR}/SHA256SUMS.txt" "${LOG_DIR}/14_sha256.log"
echo "ALL 14 STEPS COMPLETED WITH EXIT CODE 0."
