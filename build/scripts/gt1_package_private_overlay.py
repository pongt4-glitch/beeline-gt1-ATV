#!/usr/bin/env python3
"""Create a verified PRIVATE GT1 full-ROM source overlay for a Linux build host.

The staging Git commit and precisely 17 verified device proprietary files are
bundled locally. Never uploads, flashes, or writes to the Android device.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

PUBLIC_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_VENDOR_ROOT = {"Android.mk", "BoardConfigVendor.mk", "gt1v30-vendor.mk"}


def digest(path: Path):
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def run(*cmd):
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return proc.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private-vendor", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    src = args.private_vendor.resolve()
    out_dir = args.out_dir.resolve()
    if not src.is_dir() or not (src / "proprietary").is_dir():
        raise SystemExit("Private vendor source missing")
    if out_dir == PUBLIC_ROOT or PUBLIC_ROOT in out_dir.parents:
        raise SystemExit("Refusing to place the PRIVATE bundle inside the public Git repository")

    manifest = PUBLIC_ROOT / "device/amlogic/gt1v30/proprietary-files.txt"
    expected = set(ALLOWED_VENDOR_ROOT)
    for item in manifest.read_text().splitlines():
        item = item.strip()
        if not item or item.startswith("#"):
            continue
        rel = item.split("|", 1)[0].split(":", 1)[0]
        expected.add("proprietary/" + rel)

    actual = {
        p.relative_to(src).as_posix() for p in src.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(src).parts
        and p.name not in (".DS_Store",)
    }
    if actual != expected:
        raise SystemExit(
            f"Private source includes unknown/missing files: "
            f"unknown={sorted(actual-expected)}, missing={sorted(expected-actual)}"
        )

    check = PUBLIC_ROOT / "build/scripts/gt1_validate_vendor_blobs.py"
    subprocess.run([
        "python3", str(check),
        "--manifest", str(manifest),
        "--vendor-root", str(src / "proprietary"),
    ], check=True)

    commit = run("git", "-C", str(PUBLIC_ROOT), "rev-parse", "--short=12", "HEAD").decode().strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"gt1v30-private-fullrom-overlay-{commit}.tar.gz"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing archive: {target}")

    with tempfile.TemporaryDirectory(prefix="gt1-private-package-") as td:
        tree = Path(td)
        blob = run("git", "-C", str(PUBLIC_ROOT), "archive", "--format=tar",
                   "--prefix=staging/", "HEAD")
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as pack:
            if hasattr(tarfile, "data_filter"):
                pack.extractall(tree, filter="data")
            else:
                pack.extractall(tree)

        vendor_dest = tree / "vendor/amlogic/gt1v30"
        shutil.copytree(src, vendor_dest, ignore=shutil.ignore_patterns(".git", ".DS_Store", "__pycache__"))
        instructions = tree / "README_PRIVATE_BUILD.txt"
        instructions.write_text(
            "GT1 Classic private source overlay. Keep this archive OFF PUBLIC GIT.\n"
            f"Public staging commit: {commit}\n\n"
            "Verified source components: staging/ (kernel patch series, scripts,\n"
            "device DTS, pinned manifest), vendor/amlogic/gt1v30/ (17 private\n"
            "vendor blobs + generated makefiles). No stock partition dump.\n\n"
            "On a compatible Linux x86_64 build host with ample space and RAM:\n"
            "  export GT1_PRIVATE_VENDOR_ROOT=$PWD/vendor/amlogic/gt1v30\n"
            "  export GT1_LINEAGE_ROOT=/mnt/build/lineage-19.1\n"
            "  bash staging/build/scripts/gt1_full_rom_build.sh audit\n"
            "  bash staging/build/scripts/gt1_full_rom_build.sh check-host\n"
            "After inspecting and provisioning the host:\n"
            "  bash staging/build/scripts/gt1_full_rom_build.sh sync\n"
            "  bash staging/build/scripts/gt1_full_rom_build.sh patch\n"
            "  bash staging/build/scripts/gt1_full_rom_build.sh overlay\n"
            "  bash staging/build/scripts/gt1_full_rom_build.sh rom\n\n"
            "No commands to flash, boot or alter eMMC are included.\n"
        )
        entries = sorted(p for p in tree.rglob("*") if p.is_file())
        digests = [
            f"{digest(p)}  {p.relative_to(tree).as_posix()}"
            for p in entries
        ]
        (tree / "MANIFEST_SHA256.txt").write_text("\n".join(digests) + "\n")
        with tarfile.open(target, "w:gz", compresslevel=6) as output:
            for item in sorted(tree.iterdir()):
                output.add(item, arcname=item.name, recursive=True)
        target.chmod(0o600)

    checksum = digest(target)
    target_sha = out_dir / (target.name + ".sha256")
    target_sha.write_text(f"{checksum}  {target.name}\n")
    target_sha.chmod(0o600)
    print(f"PRIVATE_BUNDLE {target}")
    print(f"SHA256 {checksum}")
    print(f"BYTES {target.stat().st_size}")
    print(f"PRIVATE_VENDOR_FILES_VERIFIED {len(expected)}")
    print("PUBLIC_GIT_UNCHANGED; DEVICE_UNCHANGED")


if __name__ == "__main__":
    main()
