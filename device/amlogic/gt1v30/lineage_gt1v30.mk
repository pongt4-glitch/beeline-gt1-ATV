#
# Copyright (C) 2022-2023 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

## Inherit from generic products, most specific first
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base.mk)

## Target Android TV Leanback profile
PRODUCT_IS_ATV := true

## Inherit from gt1v30 device configuration
$(call inherit-product, $(LOCAL_PATH)/device.mk)

## Inherit some common LineageOS Android TV stuff
$(call inherit-product, vendor/lineage/config/common_tv.mk)

PRODUCT_NAME := lineage_gt1v30
PRODUCT_DEVICE := gt1v30
PRODUCT_BRAND := Beelink
PRODUCT_MODEL := GT1
PRODUCT_MANUFACTURER := AZW

PRODUCT_GMS_CLIENTID_BASE := android-askey-tv

PRODUCT_BUILD_PROP_OVERRIDES += \
    PRODUCT_NAME=gt1v30 \
    PRIVATE_BUILD_DESC="ampere-userdebug 9 PI 20190625 test-keys"

BUILD_FINGERPRINT := Amlogic/ampere/ampere:9/PI/20190625:userdebug/release-keys
