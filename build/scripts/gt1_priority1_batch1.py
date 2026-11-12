#!/usr/bin/env python3
"""Generate a reviewable git-am patch for GT1 Kernel Priority-1 Batch 1.

Reads the exact pinned upstream blob bytes over HTTPS and verifies their Git
blob SHA-1 before applying asserted, source-specific textual edits IN MEMORY.
Never edits hardware, the working tree, or the GitHub repository.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import pathlib
import re
import sys
import urllib.request

UPSTREAM = "LineageOS/android_kernel_amlogic_linux-4.9-pie"
REF = "ffb8d9d4"
EXPECTED = {
    "net/ipv4/ip_tunnel.c": "e1271e75e107177892870728dbd1434cccd11c08",
    "lib/kobject.c": "b733a83e5294d08c8ca0e806c3209115283361e7",
    "drivers/scsi/scsi_devinfo.c": "43d4b30cbf656b7cf6ff3b936c7e4e61297ed4d0",
    "drivers/amlogic/media/vout/hdmitx/hdmi_tx_20/hdmi_tx_video.c": "b394214643b0cb0494685c8426bf8b85058d4e26",
    "drivers/amlogic/media/vout/hdmitx/hdmi_tx_20/hdmi_tx_main.c": "a835fc0ed5533f9741434059b46b772a0bf46289",
    "drivers/amlogic/media/vout/cvbs/cvbs_out.c": "e3b13d8582ae00ce3752aa7dbdb70b332c60d719",
    "drivers/net/wireless/ath/ath10k/wmi.c": "e518b640aad02a8268bff1b0daf31d7882f6341c",
    "drivers/thermal/of-thermal.c": "e92c8863acba535a73e9025030f725f4e506ae7a",
    "drivers/devfreq/devfreq.c": "db70cee71caa167706b78d0d65979bf945e33bfd",
}

# Edits are specific to the verified upstream commit; reject stale/changed input.
# Each entry is (exact old text, exact new text, expected occurrences).
EDITS = {
    "net/ipv4/ip_tunnel.c": [
        ('\t\tstrncat(name, "%d", 2);\n',
         '\t\tstrlcat(name, "%d", sizeof(name));\n', 1),
    ],
    "lib/kobject.c": [
        ('\t\tstrncpy(path + length, kobject_name(parent), cur);\n',
         '\t\tmemcpy(path + length, kobject_name(parent), cur);\n', 1),
    ],
    "drivers/scsi/scsi_devinfo.c": [
        ('\tstrncpy(to, from, min(to_length, from_length));\n',
         '\tmemcpy(to, from, min(to_length, from_length));\n', 1),
        ('\t\t\tstrncpy(&to[from_length], spaces,\n\t\t\t\tto_length - from_length);\n',
         '\t\t\tmemcpy(&to[from_length], spaces,\n\t\t\t\tto_length - from_length);\n', 1),
    ],
    "drivers/amlogic/media/vout/hdmitx/hdmi_tx_20/hdmi_tx_video.c": [
        ('\t\tlen = strlen(vend_data->vendor_name);\n'
         '\t\tstrncpy(&SPD_DB[0], vend_data->vendor_name,\n\t\t\t(len > 8) ? 8 : len);\n',
         '\t\t/* SPD_DB is a zero-padded binary InfoFrame, not a C string. */\n'
         '\t\tlen = strnlen(vend_data->vendor_name, 8);\n'
         '\t\tmemcpy(&SPD_DB[0], vend_data->vendor_name, len);\n', 1),
        ('\t\tlen = strlen(vend_data->product_desc);\n'
         '\t\tstrncpy(&SPD_DB[8], vend_data->product_desc,\n\t\t\t(len > 16) ? 16 : len);\n',
         '\t\tlen = strnlen(vend_data->product_desc, 16);\n'
         '\t\tmemcpy(&SPD_DB[8], vend_data->product_desc, len);\n', 1),
    ],
    "drivers/amlogic/media/vout/hdmitx/hdmi_tx_20/hdmi_tx_main.c": [
        ('\tif (strstr(hdev->fmt_attr, "420")) {\n'
         '\t\tif (!strstr(mode, "420"))\n'
         '\t\t\tstrncat(mode, "420", 3);\n'
         '\t}\n',
         '\tif (strstr(hdev->fmt_attr, "420")) {\n'
         '\t\tif (!strstr(mode, "420") &&\n'
         '\t\t    strlcat((char *)mode, "420", sizeof(mode)) >=\n'
         '\t\t    sizeof(mode)) {\n'
         '\t\t\tpr_warn(SYS "HDMI mode name too long for 420 suffix\\n");\n'
         '\t\t\treturn -EINVAL;\n'
         '\t\t}\n'
         '\t}\n', 1),
        ('\tif (strstr(hdev->fmt_attr, "420")) {\n'
         '\t\tif (strstr(mode, "420") == NULL)\n'
         '\t\t\tstrncat(mode, "420", 3);\n'
         '\t}\n',
         '\tif (strstr(hdev->fmt_attr, "420")) {\n'
         '\t\tif (strstr(mode, "420") == NULL &&\n'
         '\t\t    strlcat((char *)mode, "420", sizeof(mode)) >=\n'
         '\t\t    sizeof(mode)) {\n'
         '\t\t\tpr_warn(SYS "HDMI mode name too long for 420 suffix\\n");\n'
         '\t\t\treturn;\n'
         '\t\t}\n'
         '\t}\n', 1),
        ('\t\t\t\tstrncpy(attr, cs[i], strlen(cs[i]));\n',
         '\t\t\t\tmemcpy(attr, cs[i], strlen(cs[i]));\n', 1),
        ('\t\t\t\t\tstrncat(attr, cd[i], strlen(cd[i]));\n',
         '\t\t\t\t\tstrlcat(attr, cd[i], sizeof(attr));\n', 1),
    ],
    "drivers/amlogic/media/vout/cvbs/cvbs_out.c": [
        ('\t\tstrncpy(vinfo->ext_name, mode,\n\t\t\t(strlen(mode) < 32) ? strlen(mode) : 31);\n',
         '\t\tstrlcpy(vinfo->ext_name, mode, sizeof(vinfo->ext_name));\n', 1),
    ],
    "drivers/net/wireless/ath/ath10k/wmi.c": [
        ('\t\t\tstrncat(tpc_value, buff, strlen(buff));\n',
         '\t\t\tstrlcat(tpc_value, buff, sizeof(tpc_value));\n', 1),
    ],
    "drivers/thermal/of-thermal.c": [
        ('\t\t\tstrncpy(tzp->governor_name, str, THERMAL_NAME_LENGTH);\n',
         '\t\t\tstrlcpy(tzp->governor_name, str,\n'
         '\t\t\t\tsizeof(tzp->governor_name));\n', 1),
    ],
    "drivers/devfreq/devfreq.c": [
        ('\tstrncpy(devfreq->governor_name, governor_name, DEVFREQ_NAME_LEN);\n',
         '\tstrlcpy(devfreq->governor_name, governor_name,\n'
         '\t\t sizeof(devfreq->governor_name));\n', 1),
    ],
}


def get_verified_source(path: str) -> str:
    url = f"https://raw.githubusercontent.com/{UPSTREAM}/{REF}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "GT1-pinned-kernel-audit"})
    with urllib.request.urlopen(req, timeout=40) as response:
        raw = response.read()
    blob_sha = hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()
    if blob_sha != EXPECTED[path]:
        raise RuntimeError(f"Upstream blob mismatch for {path}: {blob_sha} != {EXPECTED[path]}")
    return raw.decode("utf-8")


def build_patch() -> str:
    diffs = []
    n_edits = 0
    for path, changes in EDITS.items():
        source = get_verified_source(path)
        updated = source
        for old, new, count in changes:
            actual = updated.count(old)
            if actual != count:
                raise RuntimeError(f"Unexpected match count for {path}: {actual}, expected {count}: {old!r}")
            updated = updated.replace(old, new)
            n_edits += count
        fragment = ''.join(difflib.unified_diff(
            source.splitlines(keepends=True), updated.splitlines(keepends=True),
            fromfile=f'a/{path}', tofile=f'b/{path}', n=3,
        ))
        if not fragment:
            raise RuntimeError(f"No patch for {path}")
        diffs.append(f"diff --git a/{path} b/{path}\n" + fragment)
    if n_edits != 14:
        raise RuntimeError(f"Unexpected replacements: {n_edits}")
    header = (
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: GT1 Kernel Safety <gt1-kernel@localhost>\n"
        "Date: Thu, 12 Nov 2026 15:20:00 +0700\n"
        "Subject: [PATCH] fix(kernel): harden string operations, batch 1\n\n"
        "Bound HDMI/CVBS paths and preserve fixed-width SPD/SCSI bytes.\n"
        "Avoid silently overflowing the 32-byte HDMI mode buffers.\n"
        "\n---\n"
    )
    return header + ''.join(diffs) + "\n-- \n2.39.0\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Absolute or relative target .patch path")
    args = parser.parse_args()
    out = pathlib.Path(args.output)
    if out.exists():
        raise RuntimeError(f"Refusing to overwrite: {out}")
    # All sources and every replacement are checked before creating output.
    patch = build_patch()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(patch, encoding="utf-8")
    print(f"Created {out} ({len(patch.encode('utf-8'))} bytes, 14 targeted warnings)")
    print(f"SHA256 {hashlib.sha256(patch.encode('utf-8')).hexdigest()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED (no source modified): {exc}", file=sys.stderr)
        raise SystemExit(1)
