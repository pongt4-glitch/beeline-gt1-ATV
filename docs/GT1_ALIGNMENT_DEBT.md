# GT1 Kernel 4.9 / QCA9377 — Remaining Warning Audit (after Priority 2)

Source of counts: Linux/Module build logs downloaded from GitHub Actions:
- Baseline Strict Priority 1: [43189199436](https://github.com/pongt4-glitch/beeline-gt1-ATV/actions/runs/43189199436)
- QCA patched: [43192342094](https://github.com/pongt4-glitch/beeline-gt1-ATV/actions/runs/43192342094)

| Compiler diagnostic | Baseline | After QCA patch | Interpretation |
|---|---:|---:|---|
| `stringop-truncation` + `stringop-overflow` | 0 | 0 | Strict CI gate enforced |
| `address-of-packed-member` | 211 | 161 | QCA MSDU ID pointer safely refactored (50 occurrences removed) |
| `packed-not-aligned` | 83 | 83 | Review hardware/UAPI structures before editing |
| `missing-attributes` | 16 | 16 | GCC attribute diagnostics, separate from memory alignment |
| **Total** | **310** | **260** | Other diagnostics unchanged |

## Resolved QCA issue

The packed `struct cvg_nbuf_cb` in `AIO/drivers/qcacld-new/CORE/SERVICES/COMMON/adf/linux/adf_nbuf_pvt.h` exposed `&tx_desc_id` through `NBUF_CB_ID`. The affected field is a potentially unaligned 16-bit value (observed packed offset 13 with an 8-byte pointer model). The patch loads and stores the field directly using a packed-aware lvalue, removing its conversion to an ordinary `u16 *`. All three call sites were reviewed:

- `CORE/CLD_TXRX/HTT/htt_tx.c` — load
- `CORE/CLD_TXRX/TXRX/ol_tx_send.c` — load
- `CORE/CLD_TXRX/TXRX/ol_tx_sched.c` — store

The non-HL headroom storage path remains available. No packed struct field order or wire-format layout was intentionally modified. Build and module verification passed on Ubuntu GCC 9; device runtime behavior remains untested.

## Unresolved diagnostics and next review order

1. **QCA9377 packed pointers**: `queue.h` (including `sys/queue.h`) and `DFS/src/dfs_nol.c`. Locate callers and identify whether `get_unaligned`/`put_unaligned` or packed-aware field loads are appropriate, keeping the original protocol and skb memory layout.
2. **ath10k HTT hardware descriptor**: `drivers/net/wireless/ath/ath10k/htt.h:1556` produces 19 `packed-not-aligned` warnings from `struct ath10k_htt_txbuf`. Compare `sizeof` and `offsetof` before/after any candidate edit, check DMA and firmware descriptor layouts, then test separately.
3. **SCTP UAPI**: `include/uapi/linux/sctp.h` accounts for most remaining `packed-not-aligned` warnings (54 occurrences). Existing `packed, aligned(4)` data types may be part of the stable userspace ABI. Do not change layout or alignment solely to silence a compiler diagnostic.
4. **ALSA compat and EFI**: `sound/core/pcm_compat.c`, `sound/core/control_compat.c`, `drivers/firmware/efi/vars.c` and related sites have packed-member warnings. Audit ABI/unaligned loads at individual use points.
5. **Module attributes**: 16 `missing-attributes` occurrences from `include/linux/module.h` declarations represent a separate portability/compiler-attribute task, not evidence of corrupt memory layout.

## Acceptance rules for subsequent fixes

- First reproduce each warning on the exact pinned source and toolchain; distinguish unique warning locations from repeated Header expansions.
- Fix the unsafe use sites while preserving binary buffer sizes and offsets. A reduction in warnings alone is insufficient.
- Keep a patch per logical issue, check `git am`, run CI, and compare the warning categories and `Module.symvers`/module `vermagic` with the previous build.
- Do not enable or add general `-Wno-error` flags for the diagnostic being repaired.
- **No physical boot, flashing or eMMC writes** until explicitly authorized.

This report is a static code/compiler audit. It does not establish Android 12L HAL functionality or successful device boot.
