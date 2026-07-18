# 01 — Mindset for retail algo

**Overview.** Most early confusion is not math. It is mixing up *retail survival*, *prop/HFT careers*, and *building software for its own sake*. Distilled from three r/algotrading threads you clipped (2020–2018). Treat anonymous claims of returns as noise; keep the mental models.

## Key questions these notes answered

- Do I need PhD-level math to be profitable as a retail algo trader?
- If good strategies aren't published, is learning from public material pointless?
- As a software engineer, what should I *stop* optimizing?

## Distilled answers

### 1. Advanced math is useful — not a gate

**Mental model:** Retail edge and institutional edge are different games.

| Game | What usually matters |
|------|----------------------|
| Retail / small size | Valid signal + execution + risk; market impact is small |
| Large funds / HFT MM | Impact, routing, portfolio of models, infrastructure, research process |

You need enough stats to *not fool yourself* (distributions, sample size, overfitting). You do not need stochastic calculus on day one.

Nuance worth keeping: "mathematically simple" ≠ "algorithmically simple." A system can use high-school math and still be carefully engineered (state, risk, data hygiene).

Also: **algo trading ≠ quantitative research career**. Firms often hire PhDs for *hypothesis discipline*, not because every strategy needs exotic math. Linear regression still shows up in serious shops.

### 2. "If it worked it wouldn't be published" — half true

**Mental model:** Techniques are mostly public. *Combinations* are private.

What actually tends to stay quiet:

- Exact features, weights, horizons, and risk rules *together*
- Data pipelines, order routing, ops that make a mediocre idea tradable
- Anything with a very high Sharpe that still scales

What is public and still useful:

- Building blocks (factors, TA as features, basic ML, walk-forward ideas)
- Infrastructure patterns and failure modes

So: read papers and blogs for *parts*. Edge comes from fitting parts to **your** instruments, costs, and horizon — then proving it out of sample.

Implication for you: stop hunting for one secret Reddit strategy. Start a research loop (Chapter 02) on Deribit BTC options / the market you commit to.

### 3. Software engineers: alpha before frameworks

The sharpest line from the "final words" thread:

> Work on your alpha. Trading frameworks come after.

You already have a serious framework (NautilusTrader + this repo). That is an advantage *only if* you use it to test hypotheses and review fills — not to polish architecture instead of learning the market.

Related beginner traps from those threads:

- Treating crypto as magically different (it is another asset class; data access is often easier — useful for learning)
- Jumping to deep ML before you can measure a simple signal honestly
- Confusing "intraday" with "HFT" (true HFT is latency/hardware territory; most retail "intraday" is not)
- Asking strangers for their edge (money is involved; process talk is fine, features are not)

### 4. What "success" even means

Anonymous "I make six figures" posts are unfalsifiable. Prefer metrics you can compute yourself: trade count, drawdown, Sharpe-ish risk-adjusted return, **edge after costs**. Your own journal beats other people's flex.

## How this maps to nautilus-zerodte

- You already journal and attribute learning — use that as the feedback loop, not more Medium posts.
- Gate / fee / slippage work is the retail version of "sophisticated firms win on infrastructure": make costs visible before chasing fancier signals.
- Pick one market commitment (BTC options on Deribit vs equities elsewhere) and stay long enough to learn — switching markets resets the clock.

## One-week practice (novice)

1. Write one hypothesis in one sentence ("When X, short/long Y with stop Z").
2. Define how you will know it failed (max drawdown, min trade count, edge after fees).
3. Run it in this repo's backtest path; ignore any result with too few trades (see Chapter 03).
4. Do not add a new library this week.

## Sources

- [Advanced math is not required…](https://www.reddit.com/r/algotrading/comments/g052ly/) (raw: `inbox/processed/`)
- [Some final words](https://www.reddit.com/r/algotrading/comments/96mjt2/)
- ["If something really works…"](https://www.reddit.com/r/algotrading/comments/elva48/)
