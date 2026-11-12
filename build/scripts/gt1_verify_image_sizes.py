#!/usr/bin/env python3
"""Offline Image Size & Android Sparse Image Boundary Validator.

Validates generated Android partition images against exact hardware byte limits
verified from Beelink GT1 Classic (GT-T_V30_20160831) sysfs partition_geometry.txt
and live_fdt.dtb.

Supports both raw binary images and Android Sparse Images (magic 0xED26FF3A).
Fails with exit code 1 if any required image is missing, empty, malformed,
or exceeds its hardware partition capacity (either raw file size or expanded
sparse image size).
"""
import os
import struct
import sys

SPARSE_HEADER_MAGIC = 0xED26FF3A
SPARSE_HEADER_FORMAT = "<I4H4I"  # 28 bytes

# Exact hardware limits from Beelink GT1 Classic mmcblk0 partition_geometry.txt & BoardConfig.mk
PARTITION_LIMITS = {
    "boot.img": 16 * 1024 * 1024,       # mmcblk0p11: 32,768 sectors  = 16,777,216 bytes (16 MiB)
    "dtbo.img": 8 * 1024 * 1024,        # mmcblk0p8:  16,384 sectors  = 8,388,608 bytes (8 MiB)
    "recovery.img": 24 * 1024 * 1024,   # mmcblk0p6:  49,152 sectors  = 25,165,824 bytes (24 MiB)
    "vendor.img": 320 * 1024 * 1024,    # mmcblk0p16: 655,360 sectors = 335,544,320 bytes (320 MiB)
    "odm.img": 128 * 1024 * 1024,       # mmcblk0p17: 262,144 sectors = 134,217,728 bytes (128 MiB)
    "product.img": 128 * 1024 * 1024,   # mmcblk0p19: 262,144 sectors = 134,217,728 bytes (128 MiB)
    "system.img": 1280 * 1024 * 1024,   # mmcblk0p18: 2,621,440 sects = 1,342,177,280 bytes (1280 MiB)
}


def get_image_sizes(path):
    """Returns (file_size, expanded_size, is_sparse, error_msg)."""
    try:
        file_size = os.path.getsize(path)
    except OSError as exc:
        return 0, 0, False, f"OS error reading file size: {exc}"

    if file_size <= 0:
        return file_size, 0, False, "Image file is empty (0 bytes)"

    try:
        with open(path, "rb") as f:
            header = f.read(28)
    except OSError as exc:
        return file_size, 0, False, f"OS error reading header: {exc}"

    if len(header) >= 4:
        magic = struct.unpack("<I", header[:4])[0]
        if magic == SPARSE_HEADER_MAGIC:
            if len(header) < 28:
                return file_size, 0, True, "Truncated Android sparse header (< 28 bytes)"
            (
                _magic,
                major_version,
                _minor_version,
                file_hdr_sz,
                chunk_hdr_sz,
                blk_sz,
                total_blks,
                _total_chunks,
                _image_checksum,
            ) = struct.unpack(SPARSE_HEADER_FORMAT, header)
            if major_version != 1 or file_hdr_sz < 28 or chunk_hdr_sz < 12 or blk_sz == 0:
                return (
                    file_size,
                    0,
                    True,
                    f"Invalid sparse header parameters (v={major_version}, blk_sz={blk_sz})",
                )
            expanded_size = blk_sz * total_blks
            if expanded_size <= 0:
                return file_size, expanded_size, True, "Sparse image expanded size is 0 bytes"
            return file_size, expanded_size, True, None

    return file_size, file_size, False, None


def validate_directory(out_dir, required_images=None):
    if not out_dir or not os.path.isdir(out_dir):
        print(f"[FAIL] OUT_DIR is unset or directory does not exist: {out_dir!r}", file=sys.stderr)
        return False

    if required_images is None:
        required_images = list(PARTITION_LIMITS.keys())

    all_ok = True
    for img in required_images:
        if img not in PARTITION_LIMITS:
            print(f"[FAIL] Unknown image type requested: {img}", file=sys.stderr)
            all_ok = False
            continue

        limit = PARTITION_LIMITS[img]
        path = os.path.join(out_dir, img)
        if not os.path.isfile(path):
            print(f"[FAIL] {img}: MISSING at {path} (Limit: {limit} bytes)", file=sys.stderr)
            all_ok = False
            continue

        file_sz, expanded_sz, is_sparse, err = get_image_sizes(path)
        if err is not None:
            print(f"[FAIL] {img}: {err}", file=sys.stderr)
            all_ok = False
            continue

        effective_sz = max(file_sz, expanded_sz)
        kind = "sparse" if is_sparse else "raw"
        margin_mb = (limit - effective_sz) / (1024 * 1024)

        if effective_sz > limit:
            print(
                f"[FAIL] {img} ({kind}): file={file_sz} B, expanded={expanded_sz} B "
                f"EXCEEDS limit={limit} B by {-margin_mb:.2f} MiB",
                file=sys.stderr,
            )
            all_ok = False
        else:
            print(
                f"[PASS] {img} ({kind}): file={file_sz} B, expanded={expanded_sz} B "
                f"<= limit={limit} B (Margin: +{margin_mb:.2f} MiB)"
            )

    return all_ok


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OUT_DIR", "")
    images = sys.argv[2:] if len(sys.argv) > 2 else None
    ok = validate_directory(out_dir, images)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
