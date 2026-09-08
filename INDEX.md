# INDEX - open-on-demand router

Purpose: keep context small. `CLAUDE.md` is auto-loaded on every turn and holds only the rules
that apply everywhere. Everything below is read on demand. **Find the row whose "Open when"
matches the task and read only that file.** Keep this index current when files are added or
removed.

## Entry points

| File | What it is | Open when |
| --- | --- | --- |
| `CLAUDE.md` | The constitution. Tenets as one-liners, hard rules, routing, commands. | Always loaded. Do not add anything here that is not needed on every task. |
| `INTENTS.md` | Why this project exists, what success looks like, what would prove the thesis wrong, and the open questions. | Proposing new work, deciding whether something is in scope, or reorienting after a break. |
| `README.md` | Public-facing overview, install, quick start. | Onboarding a human, or changing the public description. |

## The rules

| File | What it is | Open when |
| --- | --- | --- |
| `docs/tenets.md` | T1-T12 in full: the rule, why it exists, what it forbids, and how it is enforced (grep, test, or CI job). | You want to argue with a tenet, apply one to a grey case, or add enforcement for one. |
| `docs/engineering.md` | The high-throughput baseline: concurrency model, state ownership, bounded queues and backpressure, latency budgets, idempotency and crash-only recovery, observability, security. | Touching the order path, an actor, a queue, a reconnect path, or anything with a latency or memory profile. |
| `docs/testing.md` | The seven test layers, the rules for each, and the definition of done. | Writing or changing any test, or deciding whether a change is finished. |
| `tests/conftest.py` | Suite-wide autouse isolation: run artifacts redirected to `tmp_path` via `ZERODTE_RUNS_DIR`, plus the tripwire that fails any test writing into the repo's `runs/`. | Adding a test that writes run artifacts, or the runs/ tripwire fails and you need to know why. |
| `src/nautilus_zerodte/models/halt.py` | The operator kill switch's transport: the trip file, its payload, and the atomic write and fail-closed read. Engine-free on purpose so the CLI can import it, enforced by a test. Holds NO behaviour - nothing observes the file until H6. | Touching the kill-switch transport, or needing the reason a sentinel file was chosen over a signal or a message bus. |
| `docs/evidence.md` | The run manifest, the hash chain, and what makes a result admissible. | Citing a number, comparing two runs, or wondering whether a result can be trusted. |
| `docs/killswitch_plan.md` | **A PLAN, not a description of the code.** The full kill-switch design: what NautilusTrader already provides, the ordering on trip, tasks H0-H9 with their tests, deferred items with reasons, and open questions. Marked NOT IMPLEMENTED throughout. | Picking up the kill-switch work, or checking why an approach was chosen or rejected. Never cite it as evidence a control exists. |
| `docs/decisions.md` | Decision log. Each entry carries the decision, the reasoning, and the **reversal condition**. | Asking "why is it like this", or making a decision that future sessions must not silently undo. |

## The quant subtree - load as a set when doing math or money

| File | What it is | Open when |
| --- | --- | --- |
| `docs/quant/evaluation.md` | The back/paper testing protocol: recording, purged splits, CPCV, the trial registry, neighbourhood stability, cost stress, null baselines, deflated statistics (DSR, PSR, PBO), effective sample size, and the reporting rules. | Running a sweep, tuning a parameter, choosing a statistic, or writing up a result. **This is the core workflow of the project.** |
| `docs/quant/attribution.md` | The PnL explain specification: every term (delta, gamma, theta, vega, vanna, volga, charm, inverse-contract cross term, funding, fees, slippage), path summation, the residual definition, and the two tests that gate adoption. Also lists the defects in the current implementation. | Touching `learning/`, changing how PnL is decomposed, or deciding whether a profitable run is adoptable. |
| `docs/quant/execution.md` | Fill model, cost model, spread and slippage assumptions, queue position, participation caps, settlement at the index print, pin risk, inverse-contract quoting, and the Deribit combo close constraints. | Touching `costs/`, the backtest fee or fill model, or any edge calculation. |
| `docs/quant/risk.md` | The required guardrails and their tests, the two-dimensional spot-vol shock grid, margin and liquidation, kill switches, and the reset policy. | Touching `configs/risk/`, the greek gate, position sizing, or anything that limits loss. |

## Venue and wiring

| File | What it is | Open when |
| --- | --- | --- |
| `docs/venues.md` | Venue containment rules, how to add a coin (config only), how to add a venue, the ETH extensibility test, and the Deribit specifics that keep biting. | Adding a symbol or a venue, or finding venue knowledge somewhere it does not belong. |
| `docs/architecture.md` | Runtime contracts: config layering, node wiring, the strategy FSM and gate pipeline, the SelectorActor flow. | Wiring a node, adding an actor, or changing a message topic. |
| `docs/design/README.md` | The fuller NT-first architecture: capability mapping, phase status, venue priority, plus PlantUML sources and rendered diagrams (class, sequence, state, data model, concurrency). | Needing a picture, or checking what NautilusTrader is expected to own. Regenerate the PNGs when the `.puml` changes. |
| `docs/design/ingestion-tiers.md` | Subscription and data-fidelity tiers. | Changing what the node subscribes to or how often. |
| `docs/implementation/config-wiring.md` | As-built config resolution. | Changing how config resolves. |
| `docs/implementation/gate-boundary.md` | As-built gate boundary. | Adding or reordering a gate. |
| `docs/implementation/live-catalog-capture.md` | As-built capture of live data into the catalog. | Recording real Deribit data. |
| `docs/implementation/learning-attribution.md` | **As-built and known incomplete.** Phase 6 rule-based decomposition. Superseded as a spec by `docs/quant/attribution.md`. | Reading what the code does today, not what it should do. |

## Learning material

| Path | What it is | Open when |
| --- | --- | --- |
| `docs/faq/INDEX.md` | The "quant book": five chapters distilled from `inbox/` on retail algo mindset, the research loop, backtest honesty, resources, and papers. Pedagogy, written for a reader learning the field. | Building intuition, or looking for the plain-language version of an idea. |

**Precedence.** `docs/faq/03-backtest-honesty.md` and `docs/quant/evaluation.md` cover
overlapping ground. The FAQ explains *why*; `docs/quant/evaluation.md` is the **protocol that
governs**. Where they differ, the protocol wins and the FAQ should be updated.

## Reading notes

| Path | What it is | Open when |
| --- | --- | --- |
| `inbox/processed/` | Imported reading notes on algo trading practice, carried over from upstream. | Looking for prior art or a source for a claim. Not authoritative. |
| `.cursor/rules/ponytail.mdc` | Write the least code that works. Subordinate to `CLAUDE.md`. | Deciding how much code a change needs. |

## Where things do not go

- Do not put quant detail, guardrail tables, or protocol steps in `CLAUDE.md`. It is loaded on
  every turn, including turns that have nothing to do with them.
- Do not put rules in `docs/implementation/`. Those files describe what the code does today; the
  moment they carry a rule, the rule rots with the code.
- Do not create a new top-level `.md`. Add a row here and put the file in `docs/`.
