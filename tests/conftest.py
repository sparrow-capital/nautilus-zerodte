"""Suite-wide isolation from the operator's real run artifacts.

Running pytest from the repo root used to append NODE_START, NODE_STOP and a WARN-level
FLATTEN_REQUEST to `runs/latest.jsonl` - the same file, same schema, no provenance marker
as a real paper session, because `JournalEntry` is frozen and carries no test flag. Two
autouse fixtures below: one redirects run artifacts into tmp_path, the other fails any
test that writes into the repo's own `runs/` anyway.

Both are function-scoped on purpose. A session-scoped tripwire would tell you the suite
dirtied `runs/` without telling you which test did it.

The redirect covers everything that goes through `AppConfig.resolved_journal_path`, which
is every production caller. It does NOT cover the strategy and actor configs that default
to the literal string "runs/latest.jsonl" (`strategies/base.py`, `strategies/skeleton.py`,
`strategies/gated_skeleton.py`, `actors/selector.py`) - those never call the resolver. The
tripwire is what catches a regression there, which is why it exists as well as the seam.

Rejected alternatives, so nobody re-proposes them:

- `monkeypatch.chdir(tmp_path)`: breaks the eight tests that hand `load_config` a
  repo-relative profile path, and fails in a way that reads like a config bug.
- Monkeypatching `resolved_journal_path` itself: turns its own three tests in
  `tests/unit/test_config.py` into assertions about the patch.
- A test-only profile under `configs/profiles/`: can hold either a relative path (the same
  problem, relocated) or an absolute one that cannot be committed, and it drops a fake
  profile where `paper -c` can pick it up.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_RUNS_DIR = REPO_ROOT / "runs"


def _snapshot_runs_dir() -> tuple[bool, dict[str, tuple[int, int]]]:
    """Existence plus (size, mtime_ns) per entry - enough to see an append."""
    if not REPO_RUNS_DIR.exists():
        return (False, {})
    entries: dict[str, tuple[int, int]] = {}
    for path in sorted(REPO_RUNS_DIR.rglob("*")):
        stat = path.stat()
        entries[str(path.relative_to(REPO_RUNS_DIR))] = (stat.st_size, stat.st_mtime_ns)
    return (True, entries)


@pytest.fixture(autouse=True)
def _runs_dir_in_tmp_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point every relative run-artifact path at this test's own tmp_path."""
    monkeypatch.setenv("ZERODTE_RUNS_DIR", str(tmp_path / "runs"))


@pytest.fixture(autouse=True)
def test_repo_runs_dir_untouched(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail the test that writes into the repo's real runs/ directory.

    Named like a test because the failure it produces is the check: the seam above is what
    normally keeps `runs/` clean, and this is the thing that fails when the seam does not.
    """
    before = _snapshot_runs_dir()
    yield
    after = _snapshot_runs_dir()
    if after != before:
        raise AssertionError(
            f"{request.node.nodeid} wrote into the repo's runs/ directory "
            f"({REPO_RUNS_DIR}). Tests must not touch the operational audit trail. "
            f"Before: {before}. After: {after}."
        )


def require_catalog(path: Path) -> Path:
    """Skip unless a catalog fixture is genuinely present AND populated.

    Six integration files each grew their own copy of this guard and they had already
    diverged: three checked only `path.exists()`, three also required an actual parquet file.
    An empty-but-present catalog directory therefore SKIPPED three files and hard-FAILED the
    other three - half the integration layer disappearing quietly while the other half shouted.
    One guard, so the two halves cannot drift apart again.

    Existence alone is the weaker check and is not enough: `scripts/build_catalog_fixture.py`
    creates the directory before it writes into it.
    """
    if not path.exists() or not any(path.rglob("*.parquet")):
        pytest.skip(f"Catalog fixture not built at {path} - see scripts/build_catalog_fixture.py")
    return path
