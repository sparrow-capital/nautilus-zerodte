# 05 — Paper radar

**Overview.** The Paper Digest clip is a **bibliography of ~1000 titles**, not a reading list. Dumping it into your brain is anti-learning. This chapter keeps a tiny radar for later, plus rules for how to use papers without getting lost.

## How a novice should use papers

1. Start from a **question you already have** ("How do people measure walk-forward robustness?").
2. Read abstract → conclusion → figures. Skim method. Stop if it does not answer the question.
3. Extract **one testable idea** for this repo or reject it.
4. Never treat a paper's backtest as transferable to Deribit 0DTE without re-validation under your costs.

Most published "algo trading" papers optimize for citations or tenure, not your P&L (Chapter 01).

## Tiny watchlist (from your digest, relevance-biased)

Titles only — revisit when the matching chapter exists. No obligation to read any of these soon.

| Theme | Example titles in the dump | Your trigger to open |
|-------|----------------------------|----------------------|
| Crypto microstructure / timing | "The Quarter-Hour Effect… Cryptocurrency Futures"; "When The Clock Strikes: Algorithmic Trading in Cryptocurrency Markets" | Studying session/time-of-day effects |
| Crypto arbitrage / plumbing | "A Truckload of Satoshis: … One-Way Arbitrage" | Venue microstructure rabbit hole |
| Options + ML bots | "Algorithmic Options Trading Bot Using Machine Learning" | After you have a non-ML baseline |
| Robustness / walk-forward | "Adaptive Multi-Asset Trading… Walk-Forward Robustness Analysis" | Implementing WFA systematically |
| Microstructure review | "Empirical Market Microstructure Models: A Review…" | Learning liquidity / price formation vocabulary |
| Uncertainty / risk | "Trading Confidence: Comprehensive Uncertainty Estimation…"; "Capital and Risk Management… High Volatility" | Sizing and kill-switches |

Full dump stays archived: `inbox/processed/Paper Digest Recent Papers on Algorithmic Trading.md`.

## Explicitly deprioritize for now

- Hydrogen refueling / ESG / CEO turnover / retail margin trading in Kenya / LLM-evolved strategies — interesting academia, wrong curriculum for your next 90 days.
- "Deep RL beats the market" papers until costs, capacity, and leakage are things you can audit.

## When this chapter should grow

Add a paper only when:

- You finished an experiment and need a named technique, or
- The same confusion shows up twice in chat (Book Architect rule).
