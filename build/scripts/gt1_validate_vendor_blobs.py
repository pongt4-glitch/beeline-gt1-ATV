#!/usr/bin/env python3
"""Read-only integrity check of the user's private GT1 vendor blob checkout."""
import argparse
from pathlib import Path
import hashlib

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--vendor-root",type=Path,required=True)
    args=p.parse_args()
    root=args.vendor_root.resolve()
    assert root.is_dir(), "Missing private proprietary vendor directory"
    seen=set()
    checked=0
    for raw in args.manifest.read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith("#"):continue
        name,sep,sha=line.partition("|")
        name=name.split(":",1)[0]
        path=Path(name)
        assert not path.is_absolute() and ".." not in path.parts and name not in seen, "Unsafe/duplicate vendor path"
        seen.add(name)
        assert sep and len(sha)==40, "Missing SHA1 hash in source manifest"
        item=(root/path).resolve()
        assert item.is_relative_to(root), "Vendor path escaped root"
        assert item.is_file(), "Missing private vendor file from manifest"
        assert hashlib.sha1(item.read_bytes()).hexdigest()==sha, "Vendor hash mismatch"
        checked+=1
    assert checked==17, f"Expected 17 files, checked {checked}"
    print("PASS: 17/17 private vendor blob SHA-1 checks; no binary contents disclosed")

if __name__=="__main__":
    main()
