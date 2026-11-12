#!/usr/bin/env python3
"""Reproduce inline CI source fixes as mail patches for a future full ROM build.

All mutations are performed in disposable local clones. Source files, hardware,
eMMC and the original checkouts remain untouched. The input for every patch is
the *pinned* kernel/QCA source plus the reviewed base patch series.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

KERNEL_PIN = "ffb8d9d46aac1cde5ee5a1495aa86b62e484ac77"
QCA_PIN = "6d051c69d3b8acccc97abdbe0008c764a6901573"
DATE = "Thu, 12 Nov 2026 10:00:00 +0700"
AUTHOR = "GT1 Kernel Safety <gt1-kernel@localhost>"


def run(args: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(args, cwd=cwd, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(
            f"Command failed ({p.returncode}): {' '.join(args)}\n"
            f"{p.stdout[-2500:]}\n{p.stderr[-4500:]}"
        )
    return p.stdout


def extract_python_compat_steps(workflow: Path) -> list[str]:
    """Read exact Python heredocs in order from the reviewed workflow file."""
    lines = workflow.read_text().splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].strip() != "python3 - <<'PY_PATCH'":
            i += 1
            continue
        i += 1
        body = []
        while i < len(lines) and lines[i].strip() != "PY_PATCH":
            line = lines[i]
            if line and not line.startswith("          "):
                raise ValueError(f"Unexpected YAML indentation on line {i+1}")
            body.append(line[10:] if line else "")
            i += 1
        if i >= len(lines):
            raise ValueError("Unclosed PY_PATCH block")
        code = "\n".join(body) + "\n"
        compile(code, f"{workflow.name}:heredoc-{len(blocks)+1}", "exec")
        blocks.append(code)
        i += 1
    if len(blocks) != 13:
        raise ValueError(f"Workflow changed unexpectedly: expected 13 blocks, got {len(blocks)}")
    return blocks


def clone_and_patch(local: Path, dst: Path, sha: str, patches: list[Path]):
    if not (local / ".git").exists():
        raise ValueError(f"Missing local Git checkout: {local}")
    if run(["git", "-C", str(local), "cat-file", "-t", sha]).strip() != "commit":
        raise ValueError(f"Pinned commit not available locally: {sha}")
    run(["git", "clone", "--quiet", "--shared", "--no-hardlinks", str(local), str(dst)])
    run(["git", "-C", str(dst), "checkout", "--quiet", "--detach", sha])
    unexpected = run(["git", "-C", str(dst), "status", "--porcelain"])
    if unexpected:
        raise ValueError(f"Clone is not clean after pinned checkout: {unexpected[:800]}")
    # No writes to the original local repo; all actions are in dst.
    run(["git", "-C", str(dst), "-c", "user.name=GT1 Validator",
         "-c", "user.email=gt1-validator@localhost",
         "am", *(str(p) for p in patches)])


def patch_for(dst: Path, subject: str, description: str) -> tuple[str, list[str]]:
    run(["git", "-C", str(dst), "diff", "--check"])
    modified = run(["git", "-C", str(dst), "diff", "--name-only"]).splitlines()
    if not modified:
        raise ValueError(f"No inline compatibility changes produced for {dst}")
    changes = run(["git", "-C", str(dst), "diff", "--binary", "--no-ext-diff"])
    if not changes.startswith("diff --git "):
        raise ValueError("Git diff format unexpected")
    header = (
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        f"From: {AUTHOR}\nDate: {DATE}\nSubject: [PATCH] {subject}\n\n"
        f"{description}\n\n---\n"
    )
    return header + changes + "\n-- \n2.39.0\n", modified


def build(staging: Path, local_kernel: Path, local_qca: Path):
    kernel_patches = sorted((staging / "build/ci-staging/patches/kernel").glob("*.patch"))
    qca_patches = sorted((staging / "build/ci-staging/patches/qca9377").glob("*.patch"))
    if len(kernel_patches) != 6 or len(qca_patches) != 2:
        raise ValueError(f"Expected kernel patches 6 and QCA patches 2; found "
                         f"{len(kernel_patches)} and {len(qca_patches)}")
    steps = extract_python_compat_steps(staging / ".github/workflows/kernel-build.yml")

    with tempfile.TemporaryDirectory(prefix="gt1-rom-compat-") as td:
        root = Path(td)
        a, b = root / "GT1_Case_Probe", root / "gt1_case_probe"
        a.write_text("upper")
        b.write_text("lower")
        if a.read_text() != "upper" or b.read_text() != "lower":
            raise ValueError(
                f"CASE-INSENSITIVE FILESYSTEM at {root}. "
                "Linux kernel has case-colliding tracked file paths; "
                "use a case-sensitive APFS disk image or Linux ext4 volume."
            )
        a.unlink()
        b.unlink()
        kernel = root / "kernel/amlogic/linux-4.9-pie"
        qca = root / "hardware/amlogic/kernel-modules/qca9377"
        kernel.parent.mkdir(parents=True)
        qca.parent.mkdir(parents=True)
        clone_and_patch(local_kernel, kernel, KERNEL_PIN, kernel_patches)
        clone_and_patch(local_qca, qca, QCA_PIN, qca_patches)
        for i, code in enumerate(steps, start=1):
            run([sys.executable, "-c", code], cwd=root)
            print(f"PASS inline source step {i}/{len(steps)}", flush=True)

        kpatch, kfiles = patch_for(kernel, "fix(kernel): mirror CI GCC9 and Amlogic compatibility",
                                   "Capture the tested inline CI source edits for full ROM builds.")
        qpatch, qfiles = patch_for(qca, "fix(qca9377): mirror CI SME and SAP compatibility",
                                   "Carry the tested inline CI source edits into full ROM builds.")

        return {
            "kernel": (kpatch, kfiles),
            "qca": (qpatch, qfiles),
            "inline_source_sha256": hashlib.sha256(
                "::GT1_STEP::".join(steps).encode()
            ).hexdigest(),
            "steps": len(steps),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--kernel-source", type=Path, required=True)
    ap.add_argument("--qca-source", type=Path, required=True)
    ap.add_argument("--verify", action="store_true",
                    help="Compare with existing checked-in patches; do not write")
    args = ap.parse_args()
    staging = args.staging.resolve()
    sources = build(staging, args.kernel_source.resolve(), args.qca_source.resolve())
    output = {
        "kernel": staging / "build/rom-compat-patches/kernel/0007-kernel-ci-compatibility.patch",
        "qca": staging / "build/rom-compat-patches/qca9377/0003-qca-ci-compatibility.patch",
    }
    for component in ("kernel", "qca"):
        body, files = sources[component]
        dest = output[component]
        if args.verify:
            if not dest.is_file() or dest.read_text() != body:
                raise SystemExit(f"FAIL: compatibility patch differs: {dest}")
        else:
            if dest.exists():
                raise SystemExit(f"Refusing to overwrite existing compatibility patch: {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        print(f"{'VERIFY' if args.verify else 'WRITE'} {component} "
              f"files={len(files)} bytes={len(body.encode())} "
              f"sha256={hashlib.sha256(body.encode()).hexdigest()}")
        for file in files:
            print("  " + file)
    manifest = {
        "kernel_pinned_commit": KERNEL_PIN,
        "qca_pinned_commit": QCA_PIN,
        "inline_source_sha256": sources["inline_source_sha256"],
        "inline_compat_steps": sources["steps"],
        "patches": {
            key: {"path": str(output[key].relative_to(staging)),
                  "sha256": hashlib.sha256(sources[key][0].encode()).hexdigest(),
                  "changed_files": sources[key][1]}
            for key in ("kernel", "qca")
        },
        "verified_against_full_android_userspace": False,
    }
    mpath = staging / "build/rom-compat-patches/manifest.json"
    if args.verify:
        if not mpath.is_file() or json.loads(mpath.read_text()) != manifest:
            raise SystemExit("FAIL: manifest not identical")
        print("PASS: all compatibility patches and manifest reproduced exactly")
    else:
        mpath.write_text(json.dumps(manifest, indent=2) + "\n")
        print("WRITE", mpath)


if __name__ == "__main__":
    main()
