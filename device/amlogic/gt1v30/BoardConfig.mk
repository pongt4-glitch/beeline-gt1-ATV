#
# Copyright (C) 2022-2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from Amlogic GX common BoardConfig
include device/amlogic/gx-common/BoardConfigCommon.mk

DEVICE_PATH := device/amlogic/gt1v30

## SoC & Bootloader Identity (Verified from /proc/device-tree/amlogic-dt-id: gxm_q201_2g)
TARGET_SOC := gxm
TARGET_AMLOGIC_SOC := gxm
TARGET_BOOTLOADER_BOARD_NAME := q201
TARGET_KERNEL_ARCH := arm64
KERNEL_ARCH := arm64

## Bluetooth (Qualcomm QCA9377 Rome UART /dev/ttyS1, Reset GPIOX_17)
BOARD_BLUETOOTH_BDROID_BUILDCFG_INCLUDE_DIR := $(DEVICE_PATH)/bluetooth
BOARD_HAVE_BLUETOOTH := true
BOARD_HAVE_BLUETOOTH_QCOM := true

## DTB / Kernel (Amlogic S912 GXM - Beelink GT1 Classic GT-T_V30_20160831)
# TARGET_DTB_NAME is used by device/amlogic/common/mkdtbimg.mk on lineage-19.1
# BOARD_PROPRIETARY_DTB_NAMES is included for lineage-20 forward compatibility
TARGET_DTB_NAME := gt1_v30_2g
BOARD_PROPRIETARY_DTB_NAMES := gt1_v30_2g

## Boot Image Header Offsets (2GB DDR3 DRAM-safe — matches Stock boot.img & recovery.img)
# With BOARD_KERNEL_BASE := 0x01078000 (from BoardConfigAmlogic.mk):
#   kernel_addr  = (0x01078000 + 0x00008000) & 0xffffffff = 0x01080000 (16.5 MiB)
#   ramdisk_addr = (0x01078000 + 0xfff88000) & 0xffffffff = 0x01000000 (16.0 MiB)
#   second_addr  = (0x01078000 + 0xffe88000) & 0xffffffff = 0x00f00000 (15.0 MiB)
#   tags_addr    = (0x01078000 + 0xfef88100) & 0xffffffff = 0x00000100
#   dtb_addr     = (0x01078000 + 0x00e88000) & 0xffffffff = 0x01f00000 (31.0 MiB)
BOARD_RAMDISK_OFFSET := 0xfff88000
BOARD_SECOND_OFFSET := 0xffe88000
BOARD_TAGS_OFFSET := 0xfef88100
BOARD_MKBOOTIMG_ARGS := --kernel_offset $(BOARD_KERNEL_OFFSET) --second_offset $(BOARD_SECOND_OFFSET) --ramdisk_offset $(BOARD_RAMDISK_OFFSET) --tags_offset $(BOARD_TAGS_OFFSET) --dtb_offset $(BOARD_DTB_OFFSET) --header_version $(BOARD_BOOT_HEADER_VERSION)

## GPU (ARM Mali-T820MP3 Midgard r28p0-01rel0)
TARGET_AMLOGIC_GPU_ARCH := midgard
MALI_GPU_VARIANT := midgard
MALI_DRV_VERSION := r28p0

## Partitions (Verified from Beelink GT1 Classic mmcblk0 sysfs geometry & live_fdt.dts)
# mmcblk0p3  (cache)    = 2,293,760 sectors  = 1,174,405,120 bytes (1120 MiB)
# mmcblk0p6  (recovery) = 49,152 sectors     = 25,165,824 bytes    (24 MiB)
# mmcblk0p8  (dtbo)     = 16,384 sectors     = 8,388,608 bytes     (8 MiB)
# mmcblk0p11 (boot)     = 32,768 sectors     = 16,777,216 bytes    (16 MiB)
# mmcblk0p16 (vendor)   = 655,360 sectors    = 335,544,320 bytes   (320 MiB)
# mmcblk0p17 (odm)      = 262,144 sectors    = 134,217,728 bytes   (128 MiB)
# mmcblk0p18 (system)   = 2,621,440 sectors  = 1,342,177,280 bytes (1280 MiB)
# mmcblk0p19 (product)  = 262,144 sectors    = 134,217,728 bytes   (128 MiB)
# mmcblk0p20 (data)     = 23,384,064 sectors = 11,972,640,768 bytes (11418 MiB)
ADDITIONAL_PARTITIONS := odm product
ALL_PARTITIONS := $(CORE_PARTITIONS) $(ADDITIONAL_PARTITIONS)

BOARD_BOOTIMAGE_PARTITION_SIZE := 16777216
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 25165824
BOARD_DTBOIMG_PARTITION_SIZE := 8388608
BOARD_CACHEIMAGE_PARTITION_SIZE := 1174405120
BOARD_VENDORIMAGE_PARTITION_SIZE := 335544320
BOARD_ODMIMAGE_PARTITION_SIZE := 134217728
BOARD_PRODUCTIMAGE_PARTITION_SIZE := 134217728
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE := ext4
TARGET_COPY_OUT_PRODUCT := product
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 1342177280
BOARD_USERDATAIMAGE_PARTITION_SIZE := 11972640768

## Fstab & Recovery Fstab (GT1 V30 specific with /mnt/vendor/param and /product)
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/init-files/recovery.fstab

## SELinux Board-specific policies (QCA9377 SDIO & UART permissions)
BOARD_VENDOR_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/vendor

## Properties
TARGET_VENDOR_PROP += $(DEVICE_PATH)/vendor.prop

## Wi-Fi (Qualcomm QCA9377 SDIO 0271:0701 on sdio@d0070000)
BOARD_WLAN_DEVICE := qcwcn
BOARD_HOSTAPD_DRIVER := NL80211
BOARD_HOSTAPD_PRIVATE_LIB := lib_driver_cmd_qcwcn
BOARD_WPA_SUPPLICANT_DRIVER := NL80211
BOARD_WPA_SUPPLICANT_PRIVATE_LIB := lib_driver_cmd_qcwcn
WPA_SUPPLICANT_VERSION := VER_0_8_X
WIFI_DRIVER_MODULE_PATH := "/vendor/lib/modules/qca9377.ko"
WIFI_DRIVER_MODULE_NAME := "wlan"

## Inherit from the proprietary version
include vendor/amlogic/gt1v30/BoardConfigVendor.mk
