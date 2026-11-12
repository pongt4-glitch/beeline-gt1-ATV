# Beelink GT1 Classic — Recovery and Non-destructive Boot Trial Plan

Status: **PLAN ONLY**. Hardware boot, U-Boot environment writes, USB burning, eMMC modifications and flashing are **not authorized** by this plan.

## Verified starting point (2026-11-12)

- Stock system responds to read-only ADB as GT1u / GXM `gxm_q201_2g`, Android 9, Kernel 4.9.113.
- All 20 local partition images verified against `/Users/pong/Documents/ATV/device_dump/BACKUP_MANIFEST.sha256`. Keep copies outside the GT1.
- Boot ROM stock image: Android Boot Header v1, 2,048-byte pages, 16 MiB boot partition, no stock ramdisk and a 58,997-byte second-stage DTB.
- **Boot image compatibility blocker:** inherited `BoardConfigAmlogic.mk` currently specifies boot header v2. The extracted stock image proves v1. Confirm this particular vendor U-Boot supports the chosen header, DTB placement and ramdisk before any trial. The configured Android userspace is 32-bit `arm` while the kernel is ARM64; verify all vendor HALs/ABI compatibility.
- Current new kernel image about 10.8 MB plus DTB about 59 kB leaves roughly 5.9 million bytes for additional boot payload in the existing 16 MiB partition. Actual allowable Android 12L ramdisk size depends on header format and boot layout.
- Stock live memory range: 0..0x77ffffff; new source memory cap follows it. Strict GitHub Actions run `43196246098` validated the compiled DTB memory range, and all six artifact SHA-256 values were verified on Mac. U-Boot injection behavior must still be observed at an authorized boot.
- All 17 entries in `device/amlogic/gt1v30/proprietary-files.txt` were found under the local vendor directory and matched their SHA-1 hashes. This proves extraction integrity only; Android 12L HAL compatibility is still unverified.
- Stock baseline `out/gt1-stock-runtime-baseline.json` records kernel, network interface names, module names and current display mode without device identifiers. Ethernet carrier 0 means no link at observation time, **not** a driver failure; display mode was 576cvbs at observation time.

## Recovery prerequisites BEFORE any boot trial

1. Preserve a second SHA-256-verified copy of the 20 backed-up partitions on a separate storage device. Keep complete stock `boot.img`, `bootloader.img`, `recovery.img`, `dtbo.img`, `vbmeta.img`, `vendor.img`, `system.img` and relevant metadata together.
2. Identify a *specific* factory recovery firmware for **GT-T_V30_20160831 / 2 GB / 16 GB / QCA9377**, including official file checksum when available. Firmware for GT1 32 GB or a different Wi-Fi module must not be treated as compatible without proof.
3. Validate the physical recovery path for this exact U-Boot build, with a 3.3 V serial console/USB loader as appropriate, **before** considering internal writes. Do not assume a generic reset switch forces USB mode. Confirm if external SD boot can be selected while eMMC remains valid.
4. Obtain full LineageOS 19.1 Android TV 12L sources and a reliable large-disk build environment. Validate vendor blob Android compatibility, fstab, AVB/vbmeta, kernel modules, partitions and init before assembling a boot image.
5. Stage the proposed boot image only for offline checks: Android boot header version, addresses, page size, partitions, RAM disk layout, DTB section, checksum, ELF/vermagic/Module.symvers. Preserve the stock image unchanged. Use `build/scripts/gt1_boot_preflight.py` with `--stock-boot`, `--stock-second-dtb`, `--kernel`, `--dtb` to verify the extracted stock DTB matches `boot.img` byte-for-byte and calculate only an upper bound for the available ramdisk space.
6. Get specific permission for the first boot attempt, recording the selected entry path and exact rollback procedure. No implicit permission to reflash.

## Post-authorized *read-only* acceptance

- Capture serial boot console and early Linux `/proc/iomem`, `/proc/meminfo`, reserved memory/CMA messages. Stop the trial if any memory or watchdog problem appears.
- Confirm device tree identity and early init, block devices and partition mappings. Mount only as allowed by the test plan.
- Compare QCA9377 SDIO/wlan and Mali driver initialization with the saved stock baseline; inspect `dmesg`, module `vermagic`, interface availability and firmware load errors.
- Test HDMI output modes/EDID, analog CVBS, Ethernet PHY, Wi-Fi, Bluetooth UART, audio, IR remote and suspend/resume. Stock had inactive Ethernet carrier and 576cvbs display at observation; avoid false regressions from disconnected equipment.
- Validate Android 12L userspace, HAL services, app launch, SELinux and verified boot behavior separately; successful Linux boot is not enough.

## Sources and limitations

- U-Boot upstream Amlogic boot-flow documentation: https://docs.u-boot.org/en/latest/board/amlogic/boot-flow.html . The documented S912 BootROM order places eMMC ahead of SD/USB; exact vendor U-Boot and board override must be verified.
- LibreELEC Amlogic documentation: https://github.com/LibreELEC/documentation/blob/master/installation/amlogic.md . Modern mainline-kernel DTBs and boot schemes are not interchangeable with legacy Amlogic 4.9-kernel images.
- Beelink support forum related to this board marking: https://bbs.bee-link.com/d/10645-gt1-firmware-update/10 . This discussion does **not** certify a compatible recovery image for this specific 2/16 GB device.

**Blocker:** No complete Android TV 12L user-space image has been built, no first-boot serial log has been captured and no safe external boot or USB rescue procedure has been proven on this unit.
