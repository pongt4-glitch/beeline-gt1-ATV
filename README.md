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

## Known limitations

- This repository **does not contain** a full LineageOS/AOSP Android 12L source checkout or a complete usable Android TV 12L userspace image.
- Successful Kernel, Mali and QCA builds do not prove successful device boot, vendor HAL compatibility, framebuffer/HDMI output, suspend/resume or Wi-Fi/Bluetooth runtime behavior.
- Additional GCC 9 warnings still require a separate ABI-sensitive review (see alignment audit). Do not hide warnings or alter binary hardware/UAPI layouts to reduce a warning count.
- Stock backups and proprietary blobs remain **outside this public repository**. No Flash or device-side eMMC modification is authorized.
