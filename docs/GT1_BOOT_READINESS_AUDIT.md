# Beelink GT1 Classic — Offline Hardware / Boot Readiness Audit
Date: 2026-11-12. Mode: read-only evidence collection; **NO flash, eMMC write or device-side change**.

## Evidence
- Board: GT-T_V30_20160831, Amlogic GXM/S912, 2 GB RAM / 16 GB eMMC.
- Baseline strict build: GitHub Actions `43189199436` at `1271b2830bc93a3bbf8247f3242cf346268d2ce1`, success; 0 string-operation warnings and 310 other warnings; six artifact SHA-256 checks passed.
- Local device capture (not committed to GitHub): `/Users/pong/Documents/ATV/device_dump`.
- All **20 of 20** partition backup images matched `BACKUP_MANIFEST.sha256` via `shasum -a 256 -c` on 2026-11-12. Backups remain local.
- Live DTB: `device_dump/live_fdt.dtb` (61,440 bytes).
- Stock boot second DTB: `device_dump/partitions/boot_second_dtb.dtb` (58,997 bytes).
- CI candidate: `out/gt1-priority1-strict-43189199436/artifacts/gt1_v30_2g.dtb` (58,729 bytes, SHA-256 `32e6da81344935acbc1e73cea699d2553f66ffd47f90cf33965f2df26964bbbb`).
- Comparison: `/Users/pong/Documents/ATV/build/dtb-check/fdtcompare.py`; detailed local diff: `out/gt1-priority3-stock-dtb-diff.txt`. Phandle-value heuristic in that report produces some **false differences** for clocks and GPIO indexes. Use raw cells/provider node resolution for conclusions.
- Reproducible boot-critical check: `build/scripts/gt1_dtb_boot_audit.py`, local result `out/gt1-priority3-hardware-check.json`: 41/41 matching hardware invariants; RAM range difference reported separately (still blocked).

## QCA9377 Priority 2 — verified in CI

- Branch `fix/gt1-qca9377-safe-msdu-id` at `b044bc81af9a4fd814a24cfb5374a7f29e2a1486`; GitHub Actions run `43192342094` finished **success**.
- The fixed-width 16-bit MSDU identifier inside `struct cvg_nbuf_cb` is now accessed as a packed field value rather than through a possibly unaligned `u16 *`. The original structure field order and layout did not change; non-HL headroom fallback is retained.
- `adf_nbuf_pvt.h` `address-of-packed-member` warning occurrences **50 -> 0**. All compiler-warning occurrences **310 -> 260** (remaining: 161 address-of-packed-member, 83 packed-not-aligned, 16 missing-attributes). Zero string-operation warnings retained.
- Six artifacts in the new build passed SHA-256 verification. `gt1_v30_2g.dtb`, `mali.ko`, `Module.symvers`, and `kernel.config` have identical bytes to Strict Priority 1. `qca9377.ko` differs as expected from driver changes. `Image.gz` differs across build runs; no claim of binary reproducibility.
- A CI regression check for this precise QCA packed pointer diagnostic has been added to `.github/workflows/kernel-build.yml` for the next test run.
- Remaining alignment warnings require separate call-site and ABI audits. Warnings in UAPI, hardware descriptors or packed wire formats must not be cleared by changing struct alignment without compatibility tests.

## Structural findings
- DTB comparison (live DTB to CI candidate) has 396 vs 386 nodes, 385 common; 157 raw property differences. Most `reg` changes correspond to changing the root and `reserved-memory` `#address-cells/#size-cells` from 1/1 to 2/2; decoded physical addresses and sizes need to be compared as pairs, not byte sequences.
- Core eMMC, SDIO, SD and Ethernet register ranges and interrupts match the stock hardware after decoding cells. Ethernet `pinctrl-0` points at `/pinctrl@4b0/external_eth_pins` in both trees, despite different phandle values. Wi-Fi GPIO configuration and status match.
- Partition table `part-0` through `part-16` resolve to the same named nodes in the same order; raw numeric phandles shifted.
- Ramoops region remains at `0x07400000`, size `0x00100000`. Reserved-region sizes and alignment fields use 64-bit cells in the candidate, consistent with the changed parent cell width.
- Stock boot DTB has **no `/chosen` and no `/memory` node**; both appear in the live runtime tree. The bootloader supplies these at boot. Do not copy live bootargs into source because they include device-specific identifiers and runtime data. The candidate already declares memory statically, so check how U-Boot combines/replaces this node at runtime.
- **Unresolved memory geometry:** Bootloader-populated live stock tree has `/memory/reg=<0x0 0x78000000>` (RAM visible: 1,920 MiB). Candidate has `/memory@00000000/linux,usable-memory=<0x0 0x00100000 0x0 0x7ff00000>` (start 1 MiB, length 2,047 MiB). Candidate therefore describes a different memory range, extending to `0x80000000` instead of `0x78000000`. Memory-map/secure-reservation compatibility remains **UNCONFIRMED**.
- Linux 4.9 `drivers/of/fdt.c:early_init_dt_scan_memory` explicitly reads `linux,usable-memory` before `reg`. Presence of this property is supported by the kernel, but the **range choice** still requires validation.

## Priority 3 candidate memory cap (source-only; runtime unverified)

- Read-only ADB on the real stock GT1u (Android 9, GXM, `gxm_q201_2g`) confirmed `/proc/device-tree/memory/reg=<0 0x78000000>` and `/proc/iomem` system RAM `0x00000000..0x77ffffff`. No MAC, serial number, device credentials or bootargs were included in this report.
- Branch `fix/gt1-stock-memory-cap` adds incremental Kernel Patch `0006-arm64-dts-gt1-cap-memory-to-stock-map.patch` and updates `device/amlogic/gt1v30/dts/gt1_v30_2g.dts` to `linux,usable-memory=<0 0 0 0x78000000>` using the existing 64-bit cell layout.
- Patches `0001` to `0006` applied cleanly with `git am` to pinned `ffb8d9d4` in a disposable local clone; the resulting Kernel DTS and device DTS agreed. **Compiled-DTB CI memory-range gate PASSED** in GitHub Actions run `43196246098` (commit `5a4c037`). Six artifacts passed SHA-256; 260 warnings remain (161 packed-member, 83 packed-not-aligned, 16 missing-attributes), zero string warnings. The DTB differs from Priority 2 only in `/memory@00000000/linux,usable-memory`; Mali, QCA, Module.symvers and kernel config were byte-identical.
- This cap prevents the new DTB from describing the extra top 128 MiB of RAM outside the stock kernel's observed system RAM. It does **not** validate U-Boot's memory-node injection, overlap merging, secure monitor reservations or a successful boot. Keep the hardware boot gate blocked until device-side consent and serial capture.

## Stock Android boot image inspection
- `device_dump/partitions/boot.img` contains `ANDROID!` and Android boot header **v1**, page size **2,048**.
- `kernel_addr=0x01080000`, `ramdisk_addr=0x01000000`, `second_addr=0x00f00000`, `tags_addr=0x00000100`.
- `kernel_size=10,003,720`, `ramdisk_size=0`, `second_size=58,997`. The second payload corresponds in size to the extracted stock boot DTB.
- `device/amlogic/gt1v30/BoardConfig.mk` specifies 16 MiB boot and 24 MiB recovery partitions and matches these addresses by declared offsets.
- **New critical boot gate (read-only verified):** `device/amlogic/common/BoardConfigAmlogic.mk` specifies Android boot header **v2**, while the extracted real stock `boot.img` uses **v1** with its 58,997-byte DTB in the second-stage payload. The device's U-Boot acceptance of v2 and the correct DTB placement are **unconfirmed**. Do not force v1 or v2 without reviewing the required boot image structure and U-Boot implementation.
- **Architecture distinction:** the common BoardConfig specifies `TARGET_ARCH := arm` / `TARGET_CPU_ABI := armeabi-v7a` for Android userspace, while `TARGET_KERNEL_ARCH := arm64`. The project should be described as **ARM64 kernel with 32-bit Android userspace**, pending full ROM build/HAL validation.
- Boot-image *size fit* and valid image header are necessary but insufficient: bootloader behavior, DTB placement, Android 12L ramdisk/userspace, AVB/vbmeta and rollback must still be validated.
- The local workspace does **not** contain full LineageOS/AOSP source directories such as `build/envsetup.sh`, `frameworks/base` or `system/core`. The device tree, vendor extraction, Kernel and CI staging components alone cannot currently build a complete Android 12L system image. **No Android 12L image was built.**

## Decisions before a real boot test
1. Verify the proposed stock-capped DTB against the memory node U-Boot injects during an authorized test boot. The source cap is grounded in read-only ADB evidence, but its effective runtime behavior remains unconfirmed.
2. Assemble a complete LineageOS 19.1 userspace build environment, validate proprietary vendor blobs against Android 12L API/HAL requirements, fstab/SELinux, AVB and partition constraints.
3. Determine whether *non-destructive* boot from external media is actually supported by this exact U-Boot version. Do not assume `fastboot boot`, SD boot, or a recoverable USB path works.
4. Prepare offline boot image/header tests, serial console capture and a rollback procedure with verified stock partitions; keep the recovery path outside the device when possible.
5. Obtain separate explicit device-side authorization before any flash, partition write, bootloader environment change or eMMC operation.

## Proposed boot acceptance (after authorization)
- Serial kernel console reaches init without panic; verify DDR/CMA reservation, no `of_reserved_mem` conflicts, free memory and reserved memory map.
- Mount fstab targets read-only first; verify block devices and partition size mappings.
- Confirm USB, Ethernet PHY link, QCA9377 SDIO/Wi-Fi, Bluetooth UART, HDMI modes/EDID/CEC, IR remote, audio output and Mali driver with runtime logs.
- Verify Android 12L services/HAL, SELinux denials, system/vendor compatibility and suspend/resume before declaring usable ROM.

**Status: Kernel build + staged module verification do not establish boot-readiness. Device flashing remains blocked pending explicit approval.**
