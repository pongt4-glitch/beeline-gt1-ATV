#!/usr/bin/env python3
"""Validate the nine pinned GT1 LineageOS local-manifest projects (offline)."""
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

EXPECTED = {
    "device/amlogic/common": "c0bde920fd766903c078b2e76eaf7224d202fd93",
    "device/amlogic/gx-common": "0d9c41a92b42023fb937ca1528995a04a009e424",
    "device/amlogic/sepolicy": "4d7032a605094e1da7e7e95c6cb5927f36584ce5",
    "kernel/amlogic/linux-4.9-pie": "ffb8d9d46aac1cde5ee5a1495aa86b62e484ac77",
    "hardware/amlogic/kernel-modules/mali-driver": "e436241062014f098c12318033385bdc4e5a2fe8",
    "hardware/amlogic/kernel-modules/media-pie": "0014f0de13d86f87cae03108b13852ce4e53bb62",
    "hardware/amlogic/kernel-modules/optee-pie": "47248fb86ac2fc5fc0c75589f132a5b73bb312ee",
    "hardware/amlogic/kernel-modules/qca9377": "6d051c69d3b8acccc97abdbe0008c764a6901573",
    "vendor/amlogic": "439c00e0754af20d7c3425c5f36f7b84dab38b69",
}
REPO_NAMES = {
    "device/amlogic/common": "LineageOS/android_device_amlogic_common",
    "device/amlogic/gx-common": "LineageOS/android_device_amlogic_gx-common",
    "device/amlogic/sepolicy": "LineageOS/android_device_amlogic_sepolicy",
    "kernel/amlogic/linux-4.9-pie": "LineageOS/android_kernel_amlogic_linux-4.9-pie",
    "hardware/amlogic/kernel-modules/mali-driver": "LineageOS/android_hardware_amlogic_kernel-modules_mali-driver",
    "hardware/amlogic/kernel-modules/media-pie": "LineageOS/android_hardware_amlogic_kernel-modules_media-pie",
    "hardware/amlogic/kernel-modules/optee-pie": "LineageOS/android_hardware_amlogic_kernel-modules_optee-pie",
    "hardware/amlogic/kernel-modules/qca9377": "android_hardware_amlogic_kernel-modules_qca9377",
    "vendor/amlogic": "proprietary_vendor_amlogic",
}
REPO_REMOTES = {
    "hardware/amlogic/kernel-modules/qca9377": "g12-dev",
    "vendor/amlogic": "themuppets",
}

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: gt1_manifest_audit.py MANIFEST.xml")
    path=Path(sys.argv[1])
    tree=ET.parse(path).getroot()
    remotes={x.get("name"):x.get("fetch") for x in tree.findall("remote")}
    assert remotes.get("g12-dev") == "https://github.com/G12-Development"
    assert remotes.get("themuppets") == "https://github.com/TheMuppets"
    projects=tree.findall("project")
    assert len(projects)==len(EXPECTED), (len(projects),len(EXPECTED))
    result={}
    for p in projects:
        rel=p.get("path")
        assert rel in EXPECTED and rel not in result, f"Unexpected/duplicate path {rel}"
        assert p.get("name")==REPO_NAMES[rel], rel
        assert p.get("remote") == REPO_REMOTES.get(rel,"github"), rel
        rev=p.get("revision")
        assert re.fullmatch(r"[0-9a-f]{40}", rev or ""), rel
        assert rev==EXPECTED[rel], rel
        assert p.get("upstream")=="refs/heads/lineage-19.1", rel
        result[rel]=rev
    assert result==EXPECTED
    print(f"PASS: {len(result)} pinned LineageOS 19.1 GT1 projects; no path duplicates or drifting revisions")

if __name__=="__main__":
    main()
