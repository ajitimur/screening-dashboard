# Ticket 19 — fit the split's 22 parameters, or accept them as borrowed defaults

Throwaway prototype for [`19-fit-the-split-parameters.md`](../../issues/19-fit-the-split-parameters.md).
Builds on ticket 16's port (`split.py`, imported not modified) and ticket 09's bar cache
(`cache/` symlinks to it).

**Read [`FINDINGS.md`](FINDINGS.md) first.** Short version: only five of the twenty-two numbers can
move anything, three are provably redundant, and `TIGHT_MULT` is not a detection parameter — it is
the stop budget, which put §7 rather than list length at the centre of the ticket.

## Code

| file | what it does |
| --- | --- |
| `harness.py` | fixed sample, cached re-scans under parameter overrides, ticket 06's decile gate |
| `bill.py` | the audit — dead, discretisation, drawing-only, redundant |
| `lines.py` | instrumented line-validity test, per-clause attribution |
| `tight.py` | the `TIGHT_MULT` grid with §7 columns, eye-vs-looseness, the k range |
| `market.py` | IDX: collapsed bars, the sweep, ADR comparability |
| `shift.py` | what a §7 stop gate does to the population ticket 15 fitted on |

Run order: `bill.py` → `lines.py` → `tight.py` → `market.py` → `shift.py`. Needs `pandas numpy`
(the `venv/` symlink points at ticket 15's) and ticket 09's cache.

Scans are cached under `out/scans/`, keyed by a hash of the override set — the sweeps ask for the
same configuration from several angles, and a full pass is ~9s. Delete `out/` to force a re-scan.

`lines.py` duplicates `split.py`'s `fit_line` rather than monkeypatching it, so ticket 16's file
stays untouched; `verify()` checks the duplicate against the original and prints the agreement
(100.0000% on 53,922 candidates). If that number is not 100%, nothing in `FINDINGS.md` §2 counts.
