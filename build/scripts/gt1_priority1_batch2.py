#!/usr/bin/env python3
"""Generate the second GT1 Priority-1 patch from pinned upstream sources.

Offline-safe output only: fetch verified source bytes and create a git-am patch.
No local source files, GitHub branches, eMMC, or devices are modified.
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
    "net/bluetooth/hidp/core.c": "1811f8e7ddf40726980a3fcb11e29a6530618272",
    "drivers/hid/uhid.c": "e46f65671dec99e8bed6b1d116dd3a168a902e16",
    "drivers/amlogic/mmc/emmc_partitions.c": "77cb42a8bb7658512523c57cd478c6288449b7a1",
    "drivers/amlogic/media/vin/tvin/hdmirx/hdmi_rx_drv.c": "09f1cadeefecb1c2226d2b5f7f2bb2bc063282bb",
}

NEW_RX_PR = r'''int rx_pr(const char *fmt, ...)
{
	va_list args;
	char buf[PRINT_TEMP_BUF_SIZE];
	const char *log_fmt = fmt;
	size_t fmt_len;
	int len = 0;
	bool add_prefix;
	static bool last_break = 1;

	if (!fmt)
		return -EINVAL;

	fmt_len = strlen(fmt);
	add_prefix = last_break && fmt_len > 1;
	if (add_prefix) {
		/* Preserve the legacy prefix and leading-newline handling. */
		while (*log_fmt == '\n')
			log_fmt++;
	}
	last_break = fmt_len && fmt[fmt_len - 1] == '\n';

	if (log_level & LOG_EN) {
		if (add_prefix)
			len = scnprintf(buf, sizeof(buf), "[RX]-");
		va_start(args, fmt);
		len += vscnprintf(buf + len, sizeof(buf) - len,
				log_fmt, args);
		va_end(args);
		/* Do not pass a possibly truncated format to vprintk. */
		printk("%s", buf);
		return 0;
	}

	if (hdmirx_log_buf_size == 0)
		return 0;

	len = scnprintf(buf, sizeof(buf), "[%u] ", (unsigned int)jiffies);
	va_start(args, fmt);
	len += vscnprintf(buf + len, sizeof(buf) - len, fmt, args);
	va_end(args);

	/* vscnprintf returns bytes actually stored, not requested length. */
	return rx_pr_buf(buf, len);
}
'''.replace("'\\n'", "'\\n'")


def replacement(text: str, old: str, new: str, expected: int = 1) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} source occurrence(s), found {count}: {old[:140]!r}")
    return text.replace(old, new)


def fix_bluetooth(text: str) -> str:
    text = replacement(text, "\tint err;\n\n\tsession->rd_data = memdup_user(",
        "\tint err;\n\tsize_t name_len;\n\n\tsession->rd_data = memdup_user(")
    return replacement(text,
        "\tstrncpy(hid->name, req->name, sizeof(req->name) - 1);\n",
        "\tname_len = strnlen(req->name, sizeof(req->name) - 1);\n"
        "\tmemcpy(hid->name, req->name, name_len);\n"
        "\thid->name[name_len] = '\\0';\n")


def fix_uhid(text: str) -> str:
    specs = [("name", "name"), ("phys", "phys"), ("uniq", "uniq")]
    for dst, src in specs:
        old = (f"\tlen = min(sizeof(hid->{dst}), sizeof(ev->u.create2.{src})) - 1;\n"
               f"\tstrncpy(hid->{dst}, ev->u.create2.{src}, len);\n")
        new = (f"\tlen = min(sizeof(hid->{dst}), sizeof(ev->u.create2.{src})) - 1;\n"
               f"\tmemset(hid->{dst}, 0, len + 1);\n"
               f"\tmemcpy(hid->{dst}, ev->u.create2.{src},\n"
               f"\t       strnlen((const char *)ev->u.create2.{src}, len));\n")
        text = replacement(text, old, new)
    return text


def fix_emmc(text: str) -> str:
    helper = '''/* Preserve all 16 on-disk name bytes, including space for no NUL. */
static void copy_fixed_part_name(char *dest, const char *src)
{
\tsize_t name_len = strnlen(src, MAX_MMC_PART_NAME_LEN);

\tmemset(dest, 0, MAX_MMC_PART_NAME_LEN);
\tmemcpy(dest, src, name_len);
}

'''
    text = replacement(text,
        "static ssize_t emmc_part_table_get(struct class *class,\n",
        helper + "static ssize_t emmc_part_table_get(struct class *class,\n")
    # All 3 copies target the same fixed-size binary name field.
    pattern = re.compile(
        r"strncpy\(part_table\[part_num\]\.name,\s*tmp_table\[i\]\.name,\s*MAX_MMC_PART_NAME_LEN\);"
    )
    text, n = pattern.subn("copy_fixed_part_name(part_table[part_num].name,\n"
                           "\t\t\t\t\ttmp_table[i].name);", text)
    if n != 3:
        raise RuntimeError(f"Expected three fixed-field name copies; found {n}")
    text = replacement(text,
        "part_table = kmalloc(MAX_MMC_PART_NUM\n\t\t\t*sizeof(struct partitions), GFP_KERNEL);",
        "part_table = kcalloc(MAX_MMC_PART_NUM,\n\t\t\t sizeof(*part_table), GFP_KERNEL);")
    # Even 16 non-NUL chars must not over-read when printing a partition name.
    text = replacement(text, "name : %10s", "name : %10.16s", expected=2)
    return text


def fix_rx(text: str) -> str:
    start_anchor = "int rx_pr(const char *fmt, ...)\n"
    end_anchor = "\nstatic int log_init(int bufsize)\n"
    if text.count(start_anchor) != 1 or text.count(end_anchor) != 1:
        raise RuntimeError("Cannot uniquely locate rx_pr function")
    start = text.index(start_anchor)
    end = text.index(end_anchor, start)
    original = text[start:end]
    if original.count("strncpy(buf + 5, fmt + pos, (sizeof(buf) - 5));") != 1:
        raise RuntimeError("Unexpected HDMI RX formatting implementation")
    if original.count("pos = rx_pr_buf(buf, len);") != 1:
        raise RuntimeError("Unexpected HDMI RX ring-buffer implementation")
    return text[:start] + NEW_RX_PR + text[end:]

FIXERS = {
    "net/bluetooth/hidp/core.c": fix_bluetooth,
    "drivers/hid/uhid.c": fix_uhid,
    "drivers/amlogic/mmc/emmc_partitions.c": fix_emmc,
    "drivers/amlogic/media/vin/tvin/hdmirx/hdmi_rx_drv.c": fix_rx,
}


def get_verified_source(path: str) -> str:
    url = f"https://raw.githubusercontent.com/{UPSTREAM}/{REF}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "GT1-pinned-kernel-audit"})
    with urllib.request.urlopen(req, timeout=40) as response:
        raw = response.read()
    digest = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if digest != EXPECTED[path]:
        raise RuntimeError(f"Source SHA mismatch for {path}: {digest}")
    return raw.decode("utf-8")


def build_patch() -> str:
    diffs = []
    for path, fixer in FIXERS.items():
        old = get_verified_source(path)
        new = fixer(old)
        diff = ''.join(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f'a/{path}', tofile=f'b/{path}', n=3,
        ))
        if not diff:
            raise RuntimeError(f"No changes for {path}")
        diffs.append(f"diff --git a/{path} b/{path}\n" + diff)
    header = (
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: GT1 Kernel Safety <gt1-kernel@localhost>\n"
        "Date: Thu, 12 Nov 2026 15:20:00 +0700\n"
        "Subject: [PATCH] fix(kernel): secure remaining string operations, batch 2\n\n"
        "Preserve fixed 16-byte eMMC field semantics and bound ring-buffer\n"
        "logging; terminate user-supplied HID names safely.\n\n---\n"
    )
    return header + ''.join(diffs) + "\n-- \n2.39.0\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = pathlib.Path(args.output)
    if out.exists():
        raise RuntimeError(f"Refusing to overwrite: {out}")
    patch = build_patch()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(patch, encoding="utf-8")
    print(f"Created {out}: {len(patch.encode('utf-8'))} bytes, 8 warnings addressed")
    print(f"SHA256 {hashlib.sha256(patch.encode('utf-8')).hexdigest()}")
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED (no source modified): {exc}", file=sys.stderr)
        raise SystemExit(1)
