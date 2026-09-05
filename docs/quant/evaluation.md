# Evaluation protocol

The core workflow of this project. A parameter change is adopted only if it survives every step. The
sequence exists because **search finds noise by default**, so the burden of proof sits on the
candidate, not on the sceptic.

Read this before running a sweep, tuning a parameter, choosing a statistic, or writing up a
result.

---

## 0. The governing idea

You cannot manufacture more Deribit 0DTE history. Every evaluation consumes a finite,
non-replenishable resource: unseen data. The protocol is designed around that scarcity.

Two things follow. First, held-out data is **budgeted and accounted**, not treated as sacred and
then quietly abused. Second, the statistic reported must already contain the correction for how
hard we searched, because nobody applies a mental haircut correctly after the fact.

---

## 1. Record

Capture real Deribit data into the catalog (`docs/implementation/live-catalog-capture.md`).

**Synthetic fixtures are plumbing tests, not evidence.** `configs/profiles/backtest_btc.yaml`
sets `min_edge_after_cost_bps: -5000.0` so a synthetic fixture with unrealistic spreads can pass.
Any config that relaxes a gate carries a comment saying so, and **the harness refuses to emit a
tuning report from a run whose config disabled a gate.**

Record the raw quote and chain stream, not a derived feature set. Derived features can be
recomputed; a stream you failed to record is gone.

## 2. Split before you look

- **Walk-forward across time.** Never a random shuffle: market data is not IID and shuffling
  destroys exactly the structure a strategy claims to exploit.
- **Purge and embargo.** Remove training samples whose outcome window overlaps a test window, and
  embargo a gap after each test window before training resumes. A trade spanning a boundary leaks
  the answer across it. This is a hard requirement, not a refinement.
- **Anchored or rolling is a decision, not a default.** Anchored assumes the distant past still
  informs; rolling assumes it does not. State which and why.

## 3. Prefer CPCV to a single holdout

Combinatorially purged cross-validation gives a **distribution** of out-of-sample paths rather
than one draw. One holdout run gives a point estimate with no error bar, which is how a lucky
split becomes a strategy.

From the CPCV path distribution, compute:

- **PBO, the probability of backtest overfitting** (via CSCV): the probability that the
  configuration selected in-sample lands below median out-of-sample. **PBO above roughly 0.5 means
  the selection procedure is worse than choosing at random** and the sweep should be discarded
  rather than reported.
- The dispersion of out-of-sample performance across paths. A wide dispersion with a good mean is
  a strategy that depends on which month you started.

## 4. Sweep, and register every trial

Coarse grid or random search over a **declared** parameter space, declared before the sweep runs.

**The trial registry is program-wide and append-only.** N is not "configurations in this sweep",
it is every configuration ever evaluated against data, across every session and every person.
Selection bias compounds across time, and a registry that resets between sessions measures
nothing. The registry records: parameter set, data range, run manifest hash, and the resulting
statistic.

## 5. Neighbourhood stability

The winning configuration's neighbours must also be profitable.

**A sharp peak in parameter space is overfitting. A plateau is a signal.** Report the plateau
width, not just the peak value, and prefer the centre of a plateau to the top of a spike even
when the spike scores higher. A parameter you cannot perturb by ten percent without losing the
edge is not a parameter, it is a coincidence.

## 6. Cost stress

Re-run the candidate at:

- 2x fees,
- 2x slippage,
- fills one tick worse,
- displayed size halved.

A candidate whose edge dies under stress had an edge in the cost model, not in the market. See
`docs/quant/execution.md`.

## 7. Null baselines

"Beats zero" is not a result. The candidate must beat all of:

- **Random entry with matched trade count and holding period.** Controls for the payoff shape of
  simply being in the market.
- **A matched short strangle at the same delta.** For any premium-selling structure this is the
  real null: much of what looks like edge is just being short vol and getting paid for it until
  the jump.
- **Buy and hold the underlying**, cost-adjusted.
- **A stationary block bootstrap of the return series.** Blocks preserve autocorrelation; an IID
  shuffle destroys it and makes the null trivially easy to beat.

## 8. Deflated statistics

**Do not report a raw Sharpe ratio.** Sharpe assumes IID, near-normal returns. A short-gamma 0DTE
book is negatively skewed with fat tails, and Sharpe systematically flatters exactly that profile.

Report instead:

| Statistic | Why |
| --- | --- |
| **Probabilistic Sharpe Ratio (PSR)** | Corrects for skew, kurtosis, and sample length. Gives a probability that true Sharpe exceeds a benchmark. |
| **Deflated Sharpe Ratio (DSR)** | PSR with the benchmark set by the number of trials and the variance of the statistic across those trials. This is the number that answers "did we find this or did we search for it". |
| **PBO** (from CPCV) | Probability the selection procedure is overfitting. |
| **CVaR at 95 and 99** | Tail loss. The number that decides survivability. |
| **Max drawdown, and drawdown-to-mean-return** | Path risk, which Sharpe does not see. |
| **Effective N** | See below. |
| **Cost as a fraction of gross PnL** | If the edge is smaller than the cost model's error, the strategy is untradeable regardless of the equity curve. |

**Effective sample size, not trade count.** 0DTE gives many trades, but trades inside a regime are
heavily correlated, so the effective sample is far smaller than the count and the error bars are
far wider than they look. Report effective N adjusted for autocorrelation of the per-trade return
series, and use it in every interval. A thousand correlated trades in three regimes is closer to
three observations than to a thousand.

**Minimum backtest length.** For a target Sharpe and a given number of trials, there is a minimum
history below which an observed result is expected under the null. Compute it and state it. If
the available history is shorter, say so in the report rather than reporting the number as if it
meant something.

## 9. Holdout budget

The holdout may be opened more than once. Each opening is **registered** and counts as a trial.

- A hard budget for the program, default **10 openings**, after which the holdout is retired and
  a new one accrues from newly arrived data.
- **Never re-tune on the holdout and re-run it.** That converts it into training data, and unlike
  an honest extra look, it cannot be corrected for.

**The incorruptible holdout is forward time.** Paper trading accrues genuinely unseen data every
day and cannot be peeked at in advance. Historical holdout is a convenience; forward paper is the
real test. Budget accordingly.

## 10. Paper parity

Run the candidate on the paper node over a live window, and compare per intent against a backtest
replay of the same window. Divergence beyond tolerance is a bug to fix before the result is
trusted, not a discrepancy to note and move past. See `docs/testing.md`.

## 11. Attribution gate

Decompose the result (`docs/quant/attribution.md`). **A profitable run whose PnL has a
significantly signed residual is not adopted**, because the unexplained component is a modelling
error with a direction and it will not keep pointing our way.

## 12. Decide and write it down

Add an entry to `docs/decisions.md` with the decision, the evidence (run manifest hashes), and
the **reversal condition**: what would have to be observed for us to undo this.

---

## Reporting rules

- **Risk before return, on the page and in that order.** Every report leads with max drawdown,
  the loss distribution, the worst single trade, the worst day, and time to recovery. Return comes
  after, because that is the order in which they kill you.
- **Every number carries the run manifest hash** that produced it (`docs/evidence.md`).
- **Every point estimate carries an interval**, bootstrapped, per T2.
- **State the trial count** next to every headline statistic. A DSR reported without N is not
  interpretable.
- Report the number of configurations that were *not* reported. Selective reporting inside a
  sweep is the same bias at a smaller scale.
