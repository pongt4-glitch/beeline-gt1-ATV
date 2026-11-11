#
# Copyright (C) 2022-2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

## Platform SoC: Amlogic S912 (GXM)
TARGET_AMLOGIC_SOC := gxm

## Board-specific Init, Fstab & IR Remote Configuration
## Defined BEFORE inherit-product gx.mk so gt1v30's fstab.amlogic takes precedence
## in AOSP's first-match-wins PRODUCT_COPY_FILES deduplication.
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/init-files/fstab.amlogic:$(TARGET_COPY_OUT_VENDOR)/etc/fstab.amlogic \
    $(LOCAL_PATH)/init-files/init.amlogic.wifi_buildin.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/hw/init.amlogic.wifi_buildin.rc \
    $(LOCAL_PATH)/init-files/remote.conf:$(TARGET_COPY_OUT_VENDOR)/etc/remote.conf \
    $(LOCAL_PATH)/init-files/remote.cfg:$(TARGET_COPY_OUT_VENDOR)/etc/remote.cfg \
    $(LOCAL_PATH)/init-files/remote.tab1:$(TARGET_COPY_OUT_VENDOR)/etc/remote.tab1 \
    $(LOCAL_PATH)/init-files/remote.tab2:$(TARGET_COPY_OUT_VENDOR)/etc/remote.tab2 \
    $(LOCAL_PATH)/init-files/remote.tab3:$(TARGET_COPY_OUT_VENDOR)/etc/remote.tab3 \
    $(LOCAL_PATH)/init-files/remote-mouse.tab:$(TARGET_COPY_OUT_VENDOR)/etc/remote-mouse.tab

## Inherit from gx-common (includes PRODUCT_PACKAGES: mali, media, optee-module)
$(call inherit-product, device/amlogic/gx-common/gx.mk)

## Inherit from vendor blobs for gt1v30
$(call inherit-product, vendor/amlogic/gt1v30/gt1v30-vendor.mk)

## Overlays
DEVICE_PACKAGE_OVERLAYS += \
    $(LOCAL_PATH)/overlay

## Wi-Fi & Bluetooth Packages (64-bit source-built qca9377.ko + userspace supplicant/hostapd)
PRODUCT_PACKAGES += \
    qca9377 \
    libwpa_client \
    hostapd \
    wpa_supplicant
