#!/bin/bash
#
# Copyright (C) 2016 The CyanogenMod Project
# Copyright (C) 2017-2023 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

set -e

export DEVICE=gt1v30
export DEVICE_COMMON=gx-common
export VENDOR=amlogic
export VENDOR_COMMON=${VENDOR}
export VENDOR_DEVICE=${VENDOR}
export TARGET_SOC=gxm

"./../../${VENDOR_COMMON}/${DEVICE_COMMON}/setup-makefiles.sh" "$@"
