# 03 — Backtest honesty

**Overview.** Beautiful equity curves lie. This chapter is the "don't fool yourself" layer of the research loop — distilled from the same Wealth Hub guide, focused on pitfalls that matter for a novice in options/crypto.

## Slippage and fills

Databases love clean open/close prices. Live markets fill inside ranges — often near the **worse** side when you chase with market orders.

- Opening and closing auctions / first-last minutes are especially hostile.
- High trade count × small edge ⇒ slippage can erase the whole strategy.
- **Rule:** if your edge is a few bps, you must model costs before believing the backtest.

This repo already cares about commission vs slippage vs predicted edge — lean on that instead of assuming mid-price fills.

## Events, limits, and "weird days"

- Futures **limit moves** / circuit breakers can make "enter at stop" fantasy. Exclude locked-limit days unless the strategy is *about* events.
- Around major economic releases, slippage explodes. Either flat, widened assumptions, or an explicit event strategy.
- Crypto has its own analogues (exchange outages, funding spikes, thin books). Same principle: don't train on fantasy fills.

## Contract rolls and continuous series (futures)

If you ever backtest futures continuous charts:

| Adjustment | Preserves | Distorts |
|------------|-----------|----------|
| Unadjusted | Actual traded prices | Fake jumps on roll day |
| Difference-adjusted | Point moves | Percent returns |
| Ratio-adjusted | Percent moves | Absolute point levels |

Signals that use **points/ticks** need difference-style continuity; **%-return** logic needs ratio-style. Wrong choice silently invents alpha.

For **listed options / 0DTE**, you usually work contract-by-contract (expiry, strike) rather than a rolled continuous future — still be careful stitching quotes across sessions.

## Sample size and history window

Standard error of an average shrinks with √n. Rough practitioner floor: **≥ ~30 trades** before you talk about "a result"; more is better.

Window length vs style (guide heuristics, not dogma):

| Style | Often cited history |
|-------|---------------------|
| Short-term | ~1–2 years |
| Intermediate | ~2–4 years |
| Long-term | ~4–8 years |

Also require **diverse regimes**: congested, trending, high/low vol — not one bull tape.

Trades should be spread through time. One lucky week carrying a multi-year backtest is a fail.

## What "good" looks like before optimization

- Mild profit under normal conditions; huge unexplained losses → investigate or redesign.
- Results should match the **story** of the strategy.
- After optimization, prefer profiles where **many** nearby param sets work (wide hill), not one spike.

Pessimistic checks (ideas from the guide):

- Haircut wins / inflate losses by √n-style adjustments (PROM-style thinking).
- Drop the largest winner and recompute.
- Compare max drawdown to average drawdown; if max ≫ average, understand that episode.

Equity-curve correlation to "perfect profit" is a fancy robustness idea — optional later.

## Overfitting checklist (print this)

- [ ] Too many parameters relative to trade count
- [ ] Optimized on the same data you report as "proof"
- [ ] No walk-forward / holdout
- [ ] Costs off or unrealistically low
- [ ] Lookahead (using future info in features or labels)
- [ ] Survivorship / missing delisted or expired contracts
- [ ] One market, one regime, one lucky year

If three or more boxes are checked, the strategy is homework, not edge.

## Tie-back to learning as a novice

Your job early is not max CAGR. It is **calibration**: does live (or paper) behave like the backtest within a tolerance you wrote down in advance?

When it diverges, ask in order:

1. Bug / data / fill model?
2. Costs underestimated?
3. Regime shift?
4. Strategy was never real?

Only then change parameters — and log why.
