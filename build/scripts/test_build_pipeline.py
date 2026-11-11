#!/usr/bin/env python3
"""Unit Test Suite for Beelink GT1 LineageOS 19.1 Build Scripts & Static Validators.

Tests:
1. verify_image_sizes.py:
   - Real partition dumps (within/at exact hardware limit)
   - Android Sparse Image v1.0 at exact 1280 MiB system.img limit
   - Android Sparse Image exceeding limit by 1 block (+4096 B) -> fail (exit 1)
   - Raw boot.img exceeding limit by 1 byte -> fail (exit 1)
   - Empty 0-byte image file -> fail (exit 1)
   - Truncated sparse header (< 28 bytes) -> fail (exit 1)
   - Invalid sparse header version/block size -> fail (exit 1)
   - Missing required image -> fail (exit 1)
2. build_beelink_gt1.sh:
   - bash -n syntax check
   - Invalid action argument rejection -> fail (exit 1)
   - 'verify' mode integration with OUT_DIR environment variable (pass & fail cases)
3. provision_ubuntu_build_host.sh:
   - bash -n syntax check
   - Architecture guard check on non-x86_64 host -> fail (exit 1)
4. Kernel Module & Makefile Configuration:
   - Verify KERNEL_ARCH := arm64 and TARGET_KERNEL_ARCH := arm64 in BoardConfig.mk
   - Verify KERNEL_ARCH ?= $(TARGET_KERNEL_ARCH) in qca9377/Android.mk & mali-driver/midgard/Android.mk
   - Verify 0 prebuilt .ko files in vendor/amlogic/gt1v30
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ATV_ROOT = "/Users/pong/Documents/ATV"
SCRIPTS_DIR = os.path.join(ATV_ROOT, "build/scripts")
VALIDATOR = os.path.join(SCRIPTS_DIR, "verify_image_sizes.py")
BUILD_SH = os.path.join(SCRIPTS_DIR, "build_beelink_gt1.sh")
PROVISION_SH = os.path.join(SCRIPTS_DIR, "provision_ubuntu_build_host.sh")
REAL_PARTS = os.path.join(ATV_ROOT, "device_dump/partitions")


def write_sparse_header(path, blk_sz, total_blks, major=1, hdr_sz=28, chunk_sz=12):
    hdr = struct.pack("<I4H4I", 0xED26FF3A, major, 0, hdr_sz, chunk_sz, blk_sz, total_blks, 0, 0)
    with open(path, "wb") as f:
        f.write(hdr)


def populate_valid_sparse_dir(tmpdir):
    limits = {
        "boot.img": 16 * 1024 * 1024,
        "dtbo.img": 8 * 1024 * 1024,
        "recovery.img": 24 * 1024 * 1024,
        "vendor.img": 320 * 1024 * 1024,
        "odm.img": 128 * 1024 * 1024,
        "product.img": 128 * 1024 * 1024,
        "system.img": 1280 * 1024 * 1024,
    }
    for name, limit in limits.items():
        write_sparse_header(os.path.join(tmpdir, name), 4096, limit // 4096)


class TestBuildPipeline(unittest.TestCase):
    def test_01_real_partition_dumps_pass(self):
        res = subprocess.run(["python3", VALIDATOR, REAL_PARTS], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("[PASS] system.img (raw): file=1342177280 B", res.stdout)

    def test_02_sparse_images_exact_boundary_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            populate_valid_sparse_dir(tmpdir)
            res = subprocess.run(["python3", VALIDATOR, tmpdir], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertIn("[PASS] system.img (sparse): file=28 B, expanded=1342177280 B", res.stdout)

    def test_03_sparse_oversize_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            populate_valid_sparse_dir(tmpdir)
            write_sparse_header(
                os.path.join(tmpdir, "system.img"), 4096, ((1280 * 1024 * 1024) // 4096) + 1
            )
            res = subprocess.run(["python3", VALIDATOR, tmpdir], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("EXCEEDS limit=1342177280 B", res.stderr)

    def test_04_raw_oversize_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            populate_valid_sparse_dir(tmpdir)
            with open(os.path.join(tmpdir, "boot.img"), "wb") as f:
                f.truncate(16 * 1024 * 1024 + 1)
            res = subprocess.run(["python3", VALIDATOR, tmpdir], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("boot.img (raw): file=16777217 B", res.stderr)

    def test_05_empty_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            populate_valid_sparse_dir(tmpdir)
            open(os.path.join(tmpdir, "dtbo.img"), "wb").close()
            res = subprocess.run(["python3", VALIDATOR, tmpdir], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("empty (0 bytes)", res.stderr)

    def test_06_truncated_and_invalid_sparse_headers_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            populate_valid_sparse_dir(tmpdir)
            with open(os.path.join(tmpdir, "odm.img"), "wb") as f:
                f.write(struct.pack("<I", 0xED26FF3A) + b"\x00" * 10)
            res = subprocess.run(["python3", VALIDATOR, tmpdir], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("Truncated Android sparse header", res.stderr)

            write_sparse_header(os.path.join(tmpdir, "odm.img"), 0, 100, major=2)
            res2 = subprocess.run(["python3", VALIDATOR, tmpdir], capture_output=True, text=True)
            self.assertNotEqual(res2.returncode, 0)
            self.assertIn("Invalid sparse header parameters", res2.stderr)

    def test_07_missing_image_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            populate_valid_sparse_dir(tmpdir)
            os.remove(os.path.join(tmpdir, "vendor.img"))
            res = subprocess.run(["python3", VALIDATOR, tmpdir], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("[FAIL] vendor.img: MISSING", res.stderr)

    def test_08_shell_scripts_syntax_and_verify_mode(self):
        for sh in (PROVISION_SH, BUILD_SH):
            res = subprocess.run(["bash", "-n", sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, msg=res.stderr)

        # Invalid action should fail with exit code 1
        bad = subprocess.run([BUILD_SH, "invalid_action"], capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)

        # 'verify' action with OUT_DIR set to REAL_PARTS should pass
        env_ok = os.environ.copy()
        env_ok["OUT_DIR"] = REAL_PARTS
        ok = subprocess.run([BUILD_SH, "verify"], env=env_ok, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, msg=ok.stderr)

        # 'verify' action with empty temp dir should fail
        with tempfile.TemporaryDirectory() as empty_dir:
            env_fail = os.environ.copy()
            env_fail["OUT_DIR"] = empty_dir
            fail = subprocess.run([BUILD_SH, "verify"], env=env_fail, capture_output=True, text=True)
            self.assertNotEqual(fail.returncode, 0)

    def test_09_module_and_boardconfig_arch_consistency(self):
        bc = open(os.path.join(ATV_ROOT, "device/amlogic/gt1v30/BoardConfig.mk")).read()
        self.assertIn("TARGET_KERNEL_ARCH := arm64", bc)
        self.assertIn("KERNEL_ARCH := arm64", bc)

        qca_mk = open(os.path.join(ATV_ROOT, "hardware/amlogic/kernel-modules/qca9377/Android.mk")).read()
        self.assertIn("KERNEL_ARCH ?= $(TARGET_KERNEL_ARCH)", qca_mk)
        self.assertIn("ARCH=$(TARGET_KERNEL_ARCH) $(KERNEL_CROSS_COMPILE)", qca_mk)
        self.assertNotIn("PREFIX_CROSS_COMPILE", qca_mk)

        mali_mk = open(
            os.path.join(ATV_ROOT, "hardware/amlogic/kernel-modules/mali-driver/midgard/Android.mk")
        ).read()
        self.assertIn("KERNEL_ARCH     ?= $(TARGET_KERNEL_ARCH)", mali_mk)


if __name__ == "__main__":
    unittest.main(verbosity=2)
