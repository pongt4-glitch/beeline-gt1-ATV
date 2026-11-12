#!/usr/bin/env python3
"""Read-only Android Boot v1 header + GT1 candidate payload capacity audit.

Does not assemble boot images, write partitions, change a bootloader, or
communicate with the device. The reported ramdisk capacity is an upper bound.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ANDROID_MAGIC = b"ANDROID!"
FDT_MAGIC = 0xD00DFEED

def align(value, page):
    return ((value + page - 1) // page) * page

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-boot", type=Path, required=True)
    parser.add_argument("--stock-second-dtb", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--dtb", type=Path, required=True)
    parser.add_argument("--boot-partition-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--device-board-config", type=Path)
    parser.add_argument("--common-board-config", type=Path)
    parser.add_argument("--strict-board-header", action="store_true")
    args = parser.parse_args()
    if bool(args.device_board_config) != bool(args.common_board_config):
        parser.error("Both BoardConfig files are required for a source/header comparison")

    stock = args.stock_boot.read_bytes()
    if len(stock) < 2048 or stock[:8] != ANDROID_MAGIC:
        raise SystemExit("Not an Android Boot image")
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size,
     second_addr, tags_addr, page, version, os_version) = struct.unpack_from("<10I", stock, 8)
    if version != 1 or page not in (2048, 4096, 8192, 16384):
        raise SystemExit(f"Unexpected boot header version/page: {version}/{page}")
    if args.boot_partition_bytes > len(stock):
        raise SystemExit("Stock backup is smaller than declared boot partition")
    if len(stock) != args.boot_partition_bytes:
        raise SystemExit("Stock backup size does not equal expected boot partition")
    stock_second_offset = page + align(kernel_size, page) + align(ramdisk_size, page)
    expected_end = stock_second_offset + second_size
    if expected_end > len(stock):
        raise SystemExit("Stock boot second stage extends beyond partition")
    second = args.stock_second_dtb.read_bytes()
    if len(second) != second_size or stock[stock_second_offset:expected_end] != second:
        raise SystemExit("Extracted stock boot second-stage DTB does not match boot.img bytes")
    image = args.kernel.read_bytes()
    dtb = args.dtb.read_bytes()
    if len(dtb) < 40 or struct.unpack_from(">I", dtb)[0] != FDT_MAGIC:
        raise SystemExit("Candidate DTB has invalid FDT magic")
    advertised = struct.unpack_from(">I", dtb, 4)[0]
    if advertised > len(dtb):
        raise SystemExit("Candidate DTB FDT total size exceeds file length")
    candidate_overhead = page + align(len(image),page) + align(len(dtb),page)
    remaining = args.boot_partition_bytes - candidate_overhead
    if remaining < 0:
        raise SystemExit("Kernel + DTB do not fit the existing boot partition")
    import re

    def assignment(path: Path, key: str):
        pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*[:?+]?=\s*(\S+)")
        found = None
        for line in path.read_text().splitlines():
            m = pattern.match(line)
            if m:
                found = m.group(1)
        return found

    config = None
    if args.device_board_config:
        configured = (
            assignment(args.device_board_config, "BOARD_BOOT_HEADER_VERSION")
            or assignment(args.common_board_config, "BOARD_BOOT_HEADER_VERSION")
        )
        configured_header = int(configured, 0) if configured else None
        config = {
            "configured_boot_header_version": configured_header,
            "stock_boot_header_version": version,
            "same_header_version": configured_header == version,
            "android_userspace_arch": (
                assignment(args.device_board_config, "TARGET_ARCH")
                or assignment(args.common_board_config, "TARGET_ARCH")
            ),
            "kernel_arch": (
                assignment(args.device_board_config, "TARGET_KERNEL_ARCH")
                or assignment(args.common_board_config, "TARGET_KERNEL_ARCH")
            ),
            "bootloader_acceptance_of_new_header": "UNVERIFIED",
        }

    result = {
        "stock_boot": {
            "header_version": version, "page_bytes": page,
            "kernel_size": kernel_size, "ramdisk_size": ramdisk_size,
            "second_dtb_size": second_size,
            "kernel_addr": f"0x{kernel_addr:08x}",
            "ramdisk_addr": f"0x{ramdisk_addr:08x}",
            "second_addr": f"0x{second_addr:08x}",
            "tags_addr": f"0x{tags_addr:08x}",
            "stock_second_dtb_verified": True,
        },
        "candidate": {
            "kernel_gz_bytes": len(image),
            "dtb_bytes": len(dtb),
            "boot_partition_bytes": args.boot_partition_bytes,
            "maximum_remaining_bytes_before_ramdisk_other_sections": remaining,
            "remaining_is_upper_bound_not_verified_ramdisk_fit": True,
            "candidate_kernel_sha256": hashlib.sha256(image).hexdigest(),
            "candidate_dtb_sha256": hashlib.sha256(dtb).hexdigest(),
        },
        "status": "OFFLINE_PRECHECK_ONLY_NO_BOOT_IMAGE_CREATED"
    }
    if config is not None:
        result["board_config"] = config
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result,indent=2))
    if args.strict_board_header and config is not None and not config["same_header_version"]:
        raise SystemExit("Configured boot header differs from the verified stock version")

if __name__ == "__main__":
    main()
