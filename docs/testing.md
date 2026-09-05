# Testing and definition of done

**Every code change lands with its tests, in the same pass.** New behaviour gets a new test.
Changed behaviour gets its old test read and deliberately updated. **A bug fix gets a test that
fails on the unfixed code** - revert the fix, watch it go red, restore it.

Akash spot-checks rather than reviewing every diff, so the tests are the review. *A check that
cannot fail is not a check.*

---

## The layers

| Layer | Scope | Rules |
| --- | --- | --- |
| **Unit** | Pure functions: cost and edge math, gates, selectors, config resolution | Deterministic, no I/O, no engine. Use property tests wherever an invariant exists: a wider spread never raises edge, higher fees never raise edge, a stricter gate never admits more intents |
| **Contract** | Adapter parses and emits venue payloads correctly | Replayed from recorded frames committed as fixtures. **No network in tests, ever** |
| **Integration** | Full backtest over a fixture catalog | Asserts on journal events, not on printed output |
| **Golden** | One canonical run whose summary metrics are committed | Any metric change must be explained in the commit message. This is the layer that catches silent drift |
| **Parity** | The same window through backtest and paper | Per-intent divergence within tolerance. A parity failure is an adapter or cost-model bug (T4), never something to patch in strategy code |
| **Load** | Synthetic tick storm at N messages per second | p99 stage latency within budget, no unbounded memory growth, no dropped messages below the configured bound |
| **Failure injection** | Disconnect, stale data, partial fill, duplicate fill, venue rejection, clock jump, reconciliation mismatch | The system halts or rejects. It never trades through the fault |

## Rules that apply to all layers

- **Tests never sleep on wall-clock time.** Use the engine test clock (T3).
- **Determinism check.** The golden run executes twice in CI and the journals are diffed (T2).
- **Fixtures are small, recorded, and committed.** A test needing a large catalog is an
  integration script under `scripts/`, not a test.
- **A test that has been flaky twice is fixed or deleted the same day.** A suite people learn to
  re-run is a suite that has stopped catching things.
- **Guardrail coverage is enforced.** Every row in the table in `docs/quant/risk.md` has a test
  that trips it, and CI fails if a listed guardrail has none.
- **Grep checks in CI** for the structural tenets: no wall-clock reads outside `node/adapters/`
  (T3), no mode flags inside `strategies/`, `gates/`, `actors/` (T4), no venue literals outside
  the four allowed directories (`docs/venues.md`).
- `make lint && make test` is green before any commit. CI additionally runs the golden run.

---

## Definition of done

A change is done when all of these hold:

1. It does the thing, verified **in a running node or a real backtest run, not from reading the
   diff**.
2. It has its tests, and for a bug fix the test was watched failing first.
3. `make lint && make test` is green, and the golden run either matches or its change is
   explained.
4. Journal events for the new path exist and are traceable by `intent_id`.
5. New config knobs have a default, a documented range, and a stated reason for the default.
6. Nothing venue-specific leaked outside the four allowed directories.
7. **If it touches the order path:** a note on allocation, blocking, and what happens when it
   raises.
8. **If it changes cost, sizing, or risk:** a before-and-after on a replayed run is included, with
   run manifest hashes (`docs/evidence.md`).
9. **If it changes a decision:** an entry in `docs/decisions.md` with a reversal condition.
