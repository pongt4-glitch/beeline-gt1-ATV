#!/usr/bin/env python3
"""Verify ROM-only CI compatibility mail patches match their pinned manifest."""
import hashlib
import json
from pathlib import Path
import sys

EXPECTED = {
    "kernel": ("build/rom-compat-patches/kernel/0007-kernel-ci-compatibility.patch",16),
    "qca": ("build/rom-compat-patches/qca9377/0003-qca-ci-compatibility.patch",2),
}

def main():
    if len(sys.argv)!=3:
        raise SystemExit("Usage: gt1_rom_compat_manifest_audit.py manifest.json staging-root")
    mf=Path(sys.argv[1]).resolve()
    root=Path(sys.argv[2]).resolve()
    obj=json.loads(mf.read_text())
    assert obj["inline_compat_steps"]==13
    assert obj["kernel_pinned_commit"]=="ffb8d9d46aac1cde5ee5a1495aa86b62e484ac77"
    assert obj["qca_pinned_commit"]=="6d051c69d3b8acccc97abdbe0008c764a6901573"
    assert obj["verified_against_full_android_userspace"] is False
    from gt1_export_rom_compat import extract_python_compat_steps
    workflow=root/".github/workflows/kernel-build.yml"
    steps=extract_python_compat_steps(workflow)
    source_hash=hashlib.sha256("::GT1_STEP::".join(steps).encode()).hexdigest()
    assert source_hash==obj["inline_source_sha256"], "CI compatibility source changed since patch export"
    for kind,(name,nfiles) in EXPECTED.items():
        row=obj["patches"][kind]
        assert row["path"]==name
        assert len(row["changed_files"])==nfiles
        content=(root/name).read_bytes()
        assert hashlib.sha256(content).hexdigest()==row["sha256"], name
        assert b"diff --git a/" in content
        # The old case-insensitive Mac clone falsely deleted netfilter sources.
        assert b"deleted file mode" not in content
        assert b"new file mode" not in content
    print("PASS: 13 CI source edits retained in 16 kernel + 2 QCA files, all SHA-256 matched")

if __name__=="__main__":
    main()
