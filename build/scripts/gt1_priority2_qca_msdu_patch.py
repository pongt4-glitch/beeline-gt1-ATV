#!/usr/bin/env python3
"""Build a pinned, ABI-preserving QCA9377 MSDU ID access patch.

Reads QCA source from a local git clone at one exact commit and verifies each
Git blob before emitting an auditable mail patch. Does not edit the clone.
"""
import argparse
import difflib
import hashlib
from pathlib import Path
import subprocess

PIN = "6d051c69d3b8acccc97abdbe0008c764a6901573"
PFX = "AIO/drivers/qcacld-new/"
SOURCE_BLOBS = {
    "CORE/SERVICES/COMMON/adf/linux/adf_nbuf_pvt.h": "949af0c424f05435be466208205c4831a3bab63f",
    "CORE/SERVICES/COMMON/ol_txrx_htt_api.h": "d72dacc4460213045978aeda7cff6846a186142c",
    "CORE/CLD_TXRX/HTT/htt_tx.c": "35ad99ac86d2e9bc73ca271f4d9a310bbb79b5b4",
    "CORE/CLD_TXRX/TXRX/ol_tx_send.c": "d19266ef465c820315e6161b2beaa0370f1bb2b0",
    "CORE/CLD_TXRX/TXRX/ol_tx_sched.c": "567729d4fe259ffd6a14718e41d868659d03acca",
}

REPLACE = {
    "CORE/SERVICES/COMMON/adf/linux/adf_nbuf_pvt.h": [
        (
            """#define NBUF_CB_ID(skb) \\
    (&((struct cvg_nbuf_cb *)((skb)->cb))->tx_desc_id)""",
            """/* Use packed-aware value accesses, never a potentially unaligned u16 *. */
#define NBUF_CB_GET_ID(skb) \\
    (((struct cvg_nbuf_cb *)((skb)->cb))->tx_desc_id)
#define NBUF_CB_SET_ID(skb, value) do { \\
    ((struct cvg_nbuf_cb *)((skb)->cb))->tx_desc_id = (value); \\
} while (0)""",
        ),
    ],
    "CORE/SERVICES/COMMON/ol_txrx_htt_api.h": [
        (
            """#ifdef CONFIG_HL_SUPPORT
static inline u_int16_t *
ol_tx_msdu_id_storage(adf_nbuf_t msdu)
{
    return NBUF_CB_ID(msdu);
}
#else
static inline u_int16_t *
ol_tx_msdu_id_storage(adf_nbuf_t msdu)
{
    adf_os_assert(adf_nbuf_headroom(msdu) >= (sizeof(u_int16_t) * 2 - 1));
    return (u_int16_t *) (((adf_os_size_t) (adf_nbuf_head(msdu) + 1)) & ~0x1);
}
#endif""",
            """#ifndef CONFIG_HL_SUPPORT
/* The non-HL path stores the ID in an aligned skb headroom slot. */
static inline u_int16_t *
ol_tx_msdu_id_storage(adf_nbuf_t msdu)
{
    adf_os_assert(adf_nbuf_headroom(msdu) >= (sizeof(u_int16_t) * 2 - 1));
    return (u_int16_t *) (((adf_os_size_t) (adf_nbuf_head(msdu) + 1)) & ~0x1);
}
#endif

static inline u_int16_t
ol_tx_msdu_id_load(adf_nbuf_t msdu)
{
#ifdef CONFIG_HL_SUPPORT
    /* Direct packed-member load lets the compiler handle unaligned data. */
    return NBUF_CB_GET_ID(msdu);
#else
    return *ol_tx_msdu_id_storage(msdu);
#endif
}

static inline bool
ol_tx_msdu_id_store(adf_nbuf_t msdu, u_int16_t value)
{
#ifdef CONFIG_HL_SUPPORT
    NBUF_CB_SET_ID(msdu, value);
    return true;
#else
    u_int16_t *storage = ol_tx_msdu_id_storage(msdu);

    if (!storage)
        return false;
    *storage = value;
    return true;
#endif
}""",
        )
    ],
    "CORE/CLD_TXRX/HTT/htt_tx.c": [
        ("    u_int16_t *msdu_id_storage;\n    u_int16_t msdu_id;", "    u_int16_t msdu_id;"),
        (
            """         msdu_id_storage = ol_tx_msdu_id_storage(msdu);
         msdu_id = *msdu_id_storage;""",
            """         msdu_id = ol_tx_msdu_id_load(msdu);""",
        ),
    ],
    "CORE/CLD_TXRX/TXRX/ol_tx_send.c": [
        (
            """        u_int16_t *msdu_id_storage;
        adf_nbuf_t next;""",
            """        adf_nbuf_t next;""",
        ),
        (
            """        msdu_id_storage = ol_tx_msdu_id_storage(rejected);
        tx_desc = ol_tx_desc_find(pdev, *msdu_id_storage);""",
            """        tx_desc = ol_tx_desc_find(pdev,
                                  ol_tx_msdu_id_load(rejected));""",
        )
    ],
    "CORE/CLD_TXRX/TXRX/ol_tx_sched.c": [
        ("#define OL_TX_MSDU_ID_STORAGE_ERR(ptr) (NULL == ptr)\n\n", ""),
        ("    u_int16_t *msdu_id_storage;\n    u_int16_t msdu_id;", "    u_int16_t msdu_id;"),
        (
            """        msdu_id_storage = ol_tx_msdu_id_storage(msdu);
        if (OL_TX_MSDU_ID_STORAGE_ERR(msdu_id_storage)) {""",
            """        if (!ol_tx_msdu_id_store(msdu, msdu_id)) {""",
        ),
        (
            """        } else {
            *msdu_id_storage = msdu_id;
            num_msdus++;
        }""",
            """        } else {
            num_msdus++;
        }""",
        ),
    ]
}


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args])


def generate(source: Path):
    head = git(source, "rev-parse", "HEAD").decode().strip()
    if head != PIN:
        raise ValueError(f"Wrong source commit: {head}, expected {PIN}")
    diffs = []
    for short, sha in SOURCE_BLOBS.items():
        path = PFX + short
        raw = git(source, "show", f"{PIN}:{path}")
        blob = hashlib.sha1(f"blob {len(raw)}".encode() + bytes([0]) + raw).hexdigest()
        # Git object hashing includes a literal NUL between the header and bytes.
        if blob != sha:
            raise ValueError(f"Git blob mismatch: {path}: {blob} != {sha}")
        original = raw.decode("utf-8")
        updated = original
        for before, after in REPLACE[short]:
            hits = updated.count(before)
            if hits != 1:
                raise ValueError(f"Expected one match in {path}; saw {hits}: {before[:60]}")
            updated = updated.replace(before, after)
        patch = "".join(difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}", n=3))
        if not patch:
            raise ValueError(f"No changes for {path}")
        diffs.append(f"diff --git a/{path} b/{path}\n" + patch)
    header = (
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: GT1 Kernel Safety <gt1-kernel@localhost>\n"
        "Date: Thu, 12 Nov 2026 16:35:00 +0700\n"
        "Subject: [PATCH] fix(qca9377): access packed MSDU IDs without unaligned pointers\n\n"
        "Preserve the skb control-buffer ABI and LL headroom storage while\n"
        "using packed-aware lvalue accessors for the HL u16 descriptor ID.\n\n---\n"
    )
    return header + "".join(diffs) + "\n-- \n2.39.0\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("out/gt1-priority2-qca-source"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    patch = generate(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(patch)
    print("PATCH_GENERATED", args.output, "BYTES", len(patch.encode()),
          "SHA256", hashlib.sha256(patch.encode()).hexdigest())


if __name__ == "__main__":
    main()
