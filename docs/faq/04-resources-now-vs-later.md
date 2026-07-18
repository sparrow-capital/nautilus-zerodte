# 04 — Resources: now vs later

**Overview.** Your inbox mixed *retail learning*, *HFT engineering*, and *research bibliographies*. This chapter sorts them so you do not study FPGA networking before you can trust a backtest.

## Study now (matches your stage + this repo)

| Priority | Topic | Why |
|----------|-------|-----|
| 1 | Research loop + walk-forward (Ch 02–03) | Process > tools |
| 2 | Probability / stats: mean, variance, correlation, sample size, overfitting | Enough to not fool yourself |
| 3 | Options greeks & 0DTE intuition | Core product of this repo |
| 4 | Venue costs on Deribit (fees, spreads) | Edge after cost |
| 5 | NautilusTrader actors/strategies as *users*, not re-implementers | Ship experiments |

**Python research stack that is enough for a long time** (also what HFT researchers use *off* the critical path): IPython/Jupyter, numpy, pandas, matplotlib, scipy/statsmodels as needed. Parquet/HDF5 when datasets grow. That is the "data science laptop" world — not the exchange colo world.

## Park for later (interesting, wrong sequence)

### HFT Girl — quant research tools at an HFT firm

Useful as a **map of a professional environment**, not a shopping list:

- Prefer in-house deps on the critical path; research still uses Python/C++
- Exploration: notebooks + numpy/pandas; batch jobs on Slurm/SGE at scale
- Custom GUIs for order-book viz, packet inspection, post-trade logs
- Storage: pcaps, flat binaries, column stores (kdb/Vertica-class)
- ETL schedulers: Jenkins/cron, Airflow, etc. — pick one when you have pipelines worth scheduling

**When to reopen:** you are drowning in data/jobs, not when you lack a first signal.

### HFT Girl — top software resources for HFT developers

Latency/hardware curriculum: Agner Fog, Compiler Explorer, C++ Core Guidelines, Folly SPSC queue, LMAX Disruptor, ef_vi / FPGA manuals, FIX dictionaries, microwave network maps, Databento for book data.

**When to reopen:** you are building or interviewing for true low-latency systems. Your current Deribit 0DTE path is **not** that game (Chapter 01).

## Amberdata BTC Options PDF

Parked raw in `inbox/processed/Amberdata-BTCOptions.pdf` (~38 pages). Relevant later for BTC options market structure / data vendor framing. Not distilled yet — next Book Architect pass should turn it into an "Options & crypto data" chapter once you are ready to read vendor material with a question in mind (e.g. "what fields do I need for greeks + liquidity gates?").

## Anti-wishlist

Do not add these because a blog mentioned them:

- New backtester (you have Nautilus)
- Deep RL / LSTM "to find the signal"
- Colocation / kernel bypass
- A second market before you finish a research cycle on the first
