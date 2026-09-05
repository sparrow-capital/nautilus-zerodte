# Evidence: what makes a result citable

A number that cannot be reproduced is an anecdote. This file defines the run manifest and the
rules for admitting a result into a decision.

Read this before citing a number, comparing two runs, or wondering whether a result can be
trusted.

---

## 1. The run manifest

Every run writes a manifest into the journal before it processes its first event:

| Field | Why |
| --- | --- |
| `code_sha` | Git commit, plus a dirty flag. A dirty tree makes the run non-citable. |
| `config_resolved` | The **fully resolved** config after layering and env overrides, not the profile path. The path does not tell you what the env did to it. |
| `data_range` | Start and end timestamps of the catalog slice actually consumed. |
| `catalog_hash` | Content hash over the consumed slice. |
| `seed` | Every seed used, including any in the search harness. |
| `trial_index` | Position in the program-wide trial registry (`docs/quant/evaluation.md`). |
| `manifest_hash` | Hash over all of the above. **This is the run's identity.** |

`manifest_hash` is what a report cites. "Run 4f2a" then means something checkable rather than
something someone remembers.

## 2. Why hash it rather than record it

A recorded field can be edited after the fact, including by accident, including by a well-meaning
session tidying a report. A hash over code, config, data, and seed makes the evidence chain
**tamper-evident**: if any input changes, the identity changes, and a stale citation stops
matching instead of silently pointing at different inputs.

This matters more than it sounds when comparing sweeps across weeks. The failure it prevents is
not fraud, it is drift - the report that says one thing while the config it was generated from
has moved on.

Implementation: a manifest hash covering the ordered tuple of (code SHA, resolved config,
catalog slice hash, seed). Merkle over the catalog slice so a partial re-record can be diffed
rather than re-hashed wholesale.

## 3. Admissibility rules

A result may be cited in a tuning decision only if **all** of these hold:

1. **The manifest is complete** and the tree was clean.
2. **No gate was disabled.** Any config that relaxes a gate to pass a fixture produces a run the
   harness marks as plumbing, and a plumbing run cannot be cited. Currently
   `configs/profiles/backtest_btc.yaml` sets `min_edge_after_cost_bps: -5000.0`.
3. **The data is real**, not a synthetic fixture.
4. **Cost reconciliation is in tolerance** (T7 regression: intercept near zero, slope near one).
5. **The trial count is stated** alongside the statistic (T10).
6. **The statistic is deflated**, not raw (`docs/quant/evaluation.md` section 8).
7. **The residual test passed**, or the run is explicitly labelled diagnostic-only (T11).

A run failing any of these is still useful for debugging. It is not evidence, and it does not go
in a report as though it were.

## 4. Comparing two runs

- Compare manifests first. If the code SHA differs, the comparison is confounded unless the diff
  is understood; say which.
- Two runs on different data ranges are not comparable, however similar the ranges look.
- A metric change in the golden run is either explained in the commit message or is a regression.
  There is no third option.

## 5. Reports

- Every number carries its `manifest_hash`.
- Every point estimate carries a bootstrap interval (T2).
- Risk before return, in the order given in `docs/quant/risk.md` section 5.
- State how many configurations were evaluated and how many were not reported. Selective
  reporting inside a sweep is the same bias at a smaller scale.
