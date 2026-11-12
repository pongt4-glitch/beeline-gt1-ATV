# Beelink GT1 Classic (S912) — LineageOS 19.1 Kernel & Modules CI

Public source-only staging repository for Beelink GT1 Classic `GT-T_V30_20160831` (Amlogic S912/GXM, 2 GB RAM, 16 GB eMMC, QCA9377 wireless). Target system: Android TV 12L / LineageOS 19.1.

## Current supported scope

- Build kernel 4.9.113 and ARM64 `Image.gz`, board `gt1_v30_2g.dtb`, Mali r28p0 `mali.ko` and Qualcomm QCA9377 `qca9377.ko`.
- CI: Ubuntu 22.04, GCC **9** AArch64 cross compiler, pinned upstream kernel `LineageOS/android_kernel_amlogic_linux-4.9-pie@ffb8d9d4`, pinned QCA source `G12-Development/android_hardware_amlogic_kernel-modules_qca9377@6d051c6`.
- Kernel and QCA source compatibility changes are retained as reviewable patches and applied through GitHub Actions. The workflow verifies module symbols, manifests and targeted compiler warnings.
- Hardware DTB/boot checks are **offline**, and do not flash or write the actual eMMC.

## Documentation

- [Hardware and Boot Readiness Audit](docs/GT1_BOOT_READINESS_AUDIT.md)
- [Remaining Compiler Alignment Audit](docs/GT1_ALIGNMENT_DEBT.md)
- [Recovery and Boot Trial Plan](docs/GT1_RECOVERY_BOOT_TRIAL_PLAN.md)

## Build and verification

Run the `kernel-build.yml` workflow on a feature branch. Verify the Actions result, download its artifact and check `SHA256SUMS.txt` against all six build outputs. Static GT1-specific checks:

```bash
python3 build/scripts/gt1_dtb_boot_audit.py \
  /path/to/stock/boot_second_dtb.dtb \
  /path/to/CI/artifacts/gt1_v30_2g.dtb \
  --live-memory-dtb /path/to/stock/live_fdt.dtb
```

The separate `gt1_boot_preflight.py` validates Android Boot v1 metadata and compares an extracted stock second-stage DTB with `boot.img`; it does not create boot images.

## Full ROM source integration

A future Linux x86-64 build must apply the **same source fixes** as Kernel CI. The previous standalone full-build script did not carry all 13 inline CI GCC 9 / QCA source fixes; the verified `build/rom-compat-patches/` series and `build/scripts/gt1_full_rom_build.sh` now bridge this gap.

On the development Mac, run the **read-only** source and private blob audit:

```bash
GT1_PRIVATE_VENDOR_ROOT=/Users/pong/Documents/ATV/vendor/amlogic/gt1v30 \
  bash build/scripts/gt1_full_rom_build.sh audit
```

On a properly provisioned **Linux x86-64** machine with a case-sensitive filesystem and sufficient disk and RAM, first set `GT1_LINEAGE_ROOT` and `GT1_PRIVATE_VENDOR_ROOT`, then run `check-host`. After reviewing the results, `sync` fetches the pinned LineageOS 19.1 source, `patch` applies the reviewed Kernel/QCA/Mali mail patches, `overlay` copies board sources and private vendor files, and `rom` builds the Android package. The `all` action combines those phases **but never flashes a device**.

The local manifest is `build/manifests/gt1v30.xml` (nine pinned Git projects). `gt1_export_rom_compat.py` regenerates and verifies the 13 CI source fixes on a case-sensitive workspace. `rom-source-integration.yml` checks their portability and patch application; this is separate from a full Android compilation.

## Known limitations

- This repository **does not contain** a full LineageOS/AOSP Android 12L source checkout or a complete usable Android TV 12L userspace image.
- The inherited BoardConfig currently selects **Android Boot Header v2**, but the GT1's real stock `boot.img` uses **v1** and a second-stage DTB. The vendor U-Boot must be verified before attempting to boot a new image. Android userspace is configured as **32-bit `arm`**, while the Linux kernel is `arm64`.
- Successful Kernel, Mali and QCA builds do not prove successful device boot, vendor HAL compatibility, framebuffer/HDMI output, suspend/resume or Wi-Fi/Bluetooth runtime behavior.
- Additional GCC 9 warnings still require a separate ABI-sensitive review (see alignment audit). Do not hide warnings or alter binary hardware/UAPI layouts to reduce a warning count.
- Stock backups and proprietary blobs remain **outside this public repository**. No Flash or device-side eMMC modification is authorized.
