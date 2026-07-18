# 02 — Strategy research loop

**Overview.** A practical sequence from idea to live monitoring. Distilled from the Wealth Hub guide you clipped — stripped of order-type encyclopedia and optimizer theory you do not need yet.

## The loop (memorize this)

```text
idea → rules on paper → code → rough backtest →
robustness checks → careful optimization → walk-forward →
paper/live small → monitor → adjust or kill
```

If walk-forward fails, you do **not** tune harder. You go back to the idea.

## Elements every strategy must name

1. **Entry / exit rules** — unambiguous (no "looks oversold").
2. **Risk** — stop, max loss per trade, max portfolio heat.
3. **Position sizing** — how size scales with equity and volatility.

Capital planning (conservative starter mental model from the guide):

- Required capital ≈ `max_drawdown × ~1.5` + margin buffer (often plan for *two* bad drawdowns early).
- Fat tails break "normal" risk math; size as if your worst day can cluster.

### Position sizing — learn these first, ignore the rest for now

| Method | Idea | Novice note |
|--------|------|-------------|
| Fixed fractional | Risk x% of equity per trade | Start here |
| Volatility (ATR) | Size so a k×ATR stop ≈ your $ risk | Fits options/underlying vol regimes later |
| Kelly | Size from win rate & payoff | Upper bound; use a *fraction* of Kelly if at all |
| Martingale | Double after losses | Avoid |

Kelly sketch (guide's form):  
`Kelly% ≈ (Win% − Loss%) / (AvgWin / AvgLoss)` — treat as a ceiling, not a button to mash.

## Exit design (keep it boring)

- **Stops** limit damage; they do not guarantee fill price (gaps, crypto cascades).
- **Profit targets** often raise win rate and smooth equity; they can cut trends early. Trend systems often hate tight targets; mean-reversion / short-horizon systems use them more.
- For 0DTE options work in this repo, time decay and session end are exits whether you like it or not — model that explicitly later.

Skip the long list of exotic order types until you know which venue behaviors you actually hit (Deribit vs IB).

## From idea to first honest backtest

1. **Pseudo-code the rules** so a stranger could trade them by hand.
2. Implement; verify formulas and that fills match intent (not just that P&L looks pretty).
3. First pass: expect **mild** profitability under normal conditions. Huge early P&L is a smell.
4. Compare result to your *theory*. If behavior contradicts the story, fix the story or the bug — don't celebrate the curve.

### Multi-market / multi-timeframe (optional)

Only if the strategy claims to be general. Pick **uncorrelated** instruments. Segment history into chunks so one lucky month cannot carry the whole sample. Weak everywhere → kill early.

## Optimization — use sparingly

Optimization = search over parameters. More knobs ⇒ more ways to overfit.

**Rules of thumb from the guide (keep):**

- Optimize only **key** variables (ones that move performance). Fix the rest.
- Scan ranges that match the strategy's horizon (don't scan 1000-day lookbacks for an intraday idea).
- Prefer a **wide plateau** of decent params over a single sharp peak (spikes = fragile).
- Rough pass criteria people use: net profit > 0 and drawdown not insane (guide mentions ~20% as a soft filter — adapt to your risk).

Search methods (awareness only): grid (exhaustive, slow), hill-climbing / annealing / genetic / PSO (faster, can miss global structure). As a novice: **few parameters + grid or manual** beats fancy search.

## Walk-forward — the real exam

In-sample optimize → trade the chosen params on **unseen** data. Repeat across windows.

Answers you want:

1. Is it robust out of sample, or curve-fit?
2. What return (and drawdown) should I expect live?
3. How sensitive is it to regime change?
4. Which param set is stable enough to take forward?

Guide heuristic: walk-forward window often ~25–35% of the optimization window; short-horizon systems use shorter windows. Consistency across **several** walk-forwards matters more than one lucky OOS period. Literature cited there treats ~50–60% walk-forward efficiency as a robustness ballpark — treat as a reference, not a law.

**Shelf life:** params optimized on ~2y data may stay usable months, not forever. Plan to re-validate.

## Go-live checklist (minimal)

- [ ] Costs modeled (fees + slippage) — see Chapter 03 and this repo's learning attribution
- [ ] Kill rules written (max DD, days of underperformance, max trades/day)
- [ ] Paper or tiny size until live matches OOS within tolerance
- [ ] Journal every run; review process before P&L ego

## Map to this repo

- Config profiles + backtest path = your lab bench.
- Gates / risk = where "rules on paper" become enforceable code.
- Learning attribution = post-trade truth about what paid you (theta/gamma/vega vs costs).

Do not start by rewriting the framework. Start by writing one strategy hypothesis that can fail clearly.
