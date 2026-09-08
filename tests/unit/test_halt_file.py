"""H4: the kill switch's transport, its payload, and the config that describes it.

Two of these are guardrails and the rest are pins. The guardrails are the ones where getting it
wrong produces a kill switch that looks fine and does nothing:

- `read_trip` returning None on a file it cannot read or parse. That is fail-OPEN on the single
  control whose entire job is to stop the system, and it would be invisible until the night it
  mattered.
- `write_trip` putting its temporary file anywhere but the target directory. `os.replace` is
  atomic only within one filesystem, so a temp file under the system temp directory either
  raises EXDEV or degrades into a copy that the poller can observe half-written.

The engine-free check is not decoration either. `models/halt.py` is imported by the CLI, which
must not pull in an Actor and therefore must not import nautilus_trader - and it is what lets
this whole file be developed on a machine where nautilus_trader cannot be installed.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from nautilus_zerodte.config.strategy import AppConfig, HaltConfig
from nautilus_zerodte.models.halt import (
    HALT_FILE_SCHEMA,
    REASON_UNPARSEABLE,
    REASON_UNREADABLE,
    TripRecord,
    clear_trip,
    read_trip,
    trip_path,
    write_trip,
)

HALT_MODULE = (
    Path(__file__).resolve().parents[2] / "src" / "nautilus_zerodte" / "models" / "halt.py"
)


def _record(token: str = "tok-1", reason: str = "operator") -> TripRecord:
    return TripRecord(token=token, reason=reason, trader_id="TRADER-001")


def _imported_modules(module: Path) -> list[str]:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


# --- the module stays engine-free ------------------------------------------------------------


def test_the_import_scan_actually_found_the_module() -> None:
    """Guard the guard: a wrong path would make the engine-free check vacuously true."""
    assert HALT_MODULE.exists(), f"models/halt.py not found at {HALT_MODULE}"
    names = _imported_modules(HALT_MODULE)
    assert "pydantic" in names, f"parsed no recognisable imports from {HALT_MODULE}: {names}"


def test_models_halt_does_not_import_the_engine() -> None:
    """The CLI imports this to write the trip file, and must not drag in an Actor to do it."""
    violations = [name for name in _imported_modules(HALT_MODULE) if name.startswith("nautilus_t")]
    assert not violations, (
        "models/halt.py must not import nautilus_trader.\n  "
        + "\n  ".join(violations)
        + "\n\nThe CLI imports this module to write the trip file. An engine import here also "
        "makes it untestable on any machine without a nautilus_trader wheel."
    )


# --- read_trip fails closed ------------------------------------------------------------------


def test_read_trip_returns_none_when_the_file_is_absent(tmp_path: Path) -> None:
    """Absence is the ONLY thing that means 'no halt'."""
    assert read_trip(tmp_path / "nothing.trip") is None


def test_read_trip_on_an_unparseable_file_still_trips(tmp_path: Path) -> None:
    """GUARDRAIL. A control file we cannot parse is not a reason to keep trading (T5)."""
    path = tmp_path / "TRADER-001.trip"
    path.write_text("{not json at all", encoding="utf-8")
    record = read_trip(path)
    assert record is not None, "an unparseable trip file must still trip, not return None"
    assert record.reason == REASON_UNPARSEABLE
    assert record.trader_id == "TRADER-001", "the trader id is recoverable from the filename"


def test_read_trip_on_an_unreadable_file_still_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GUARDRAIL. Permissions, a bad disk, anything short of absence: still trip."""
    path = tmp_path / "TRADER-001.trip"
    path.write_text("{}", encoding="utf-8")

    def _raise(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("simulated I/O failure")

    monkeypatch.setattr(Path, "read_text", _raise)
    record = read_trip(path)
    assert record is not None, "an unreadable trip file must still trip, not return None"
    assert record.reason == REASON_UNREADABLE


def test_read_trip_accepts_a_record_from_a_future_schema(tmp_path: Path) -> None:
    """Deliberately not special-cased: refusing an unfamiliar version would fail open."""
    path = tmp_path / "TRADER-001.trip"
    path.write_text(
        '{"schema_version": 99, "token": "t", "reason": "operator", "trader_id": "TRADER-001"}',
        encoding="utf-8",
    )
    record = read_trip(path)
    assert record is not None
    assert record.schema_version == 99
    assert record.reason == "operator", "a future version must not be reported as unparseable"


# --- write_trip is atomic --------------------------------------------------------------------


def test_write_trip_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "TRADER-001.trip"
    write_trip(path, _record(token="abc", reason="drawdown"))
    record = read_trip(path)
    assert record is not None
    assert (record.token, record.reason, record.schema_version) == (
        "abc",
        "drawdown",
        HALT_FILE_SCHEMA,
    )


def test_write_trip_stages_its_temp_file_in_the_target_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GUARDRAIL. os.replace is atomic only within one filesystem.

    Staging under the system temp directory is the natural thing to write and it is wrong: the
    rename then either raises EXDEV or degrades into a copy, and a copy is exactly the partial
    file the poller must never see.
    """
    seen: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def _spy(src: str | Path, dst: str | Path) -> None:
        seen.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy)
    path = tmp_path / "sub" / "TRADER-001.trip"
    write_trip(path, _record())

    assert seen, "write_trip must publish via os.replace, not a plain write"
    src, dst = seen[0]
    assert src.parent == dst.parent, (
        f"temp file {src} is not in the target directory {dst.parent}; os.replace is only "
        "atomic within a single filesystem"
    )


def test_write_trip_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    path = tmp_path / "TRADER-001.trip"
    write_trip(path, _record())
    leftovers = [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")]
    assert not leftovers, f"temp files left behind: {leftovers}"


def test_write_trip_replaces_an_existing_file(tmp_path: Path) -> None:
    """A second halt overwrites the first rather than appending or failing."""
    path = tmp_path / "TRADER-001.trip"
    write_trip(path, _record(token="first"))
    write_trip(path, _record(token="second"))
    record = read_trip(path)
    assert record is not None
    assert record.token == "second"


# --- the path itself -------------------------------------------------------------------------


def test_trip_path_puts_the_trader_id_in_the_filename(tmp_path: Path) -> None:
    """GUARDRAIL. The id in the filename is what makes the hot poll a bare exists()."""
    path = trip_path(tmp_path, "TRADER-001")
    assert path.name == "TRADER-001.trip"
    assert path.parent == tmp_path / "halt"


def test_two_traders_cannot_reach_each_others_trip_file(tmp_path: Path) -> None:
    """Structural, not careful: each node only ever looks at its own fixed path."""
    assert trip_path(tmp_path, "TRADER-001") != trip_path(tmp_path, "TRADER-002")


def test_clear_trip_reports_whether_it_removed_anything(tmp_path: Path) -> None:
    path = tmp_path / "TRADER-001.trip"
    assert clear_trip(path) is False
    write_trip(path, _record())
    assert clear_trip(path) is True
    assert not path.exists()


# --- config ----------------------------------------------------------------------------------


def test_the_kill_switch_is_off_by_default() -> None:
    """base.yaml ships it off; only the paper and live profiles turn it on."""
    assert HaltConfig().enabled is False
    assert AppConfig().halt.enabled is False


def test_market_exit_budget_must_fit_inside_timeout_post_stop() -> None:
    """GUARDRAIL. A retry budget longer than the post-stop timeout races its own disconnect.

    NautilusTrader ships this as an exact 10.0s-vs-10.0s tie between the exit finishing and the
    execution clients going away. The 15.0s floor on `timeout_post_stop_secs` rules that
    particular tie out; the validator is what catches an operator lengthening the retry budget
    afterwards without touching the timeout, which is the version that arrives by accident.
    """
    with pytest.raises(ValidationError) as excinfo:
        HaltConfig(
            market_exit_interval_ms=500,
            market_exit_max_attempts=40,
            timeout_post_stop_secs=15.0,
        )
    message = str(excinfo.value)
    assert "20.0" in message, f"the failure must name the computed budget: {message}"
    assert "15.0" in message, f"the failure must name the limit it exceeded: {message}"


def test_the_default_config_is_inside_its_own_validator() -> None:
    """The defaults must not be a configuration the validator would reject."""
    config = HaltConfig()
    budget = config.market_exit_interval_ms * config.market_exit_max_attempts / 1000
    assert budget < config.timeout_post_stop_secs


@pytest.mark.parametrize("poll_secs", [0.0, 0.1, 5.5])
def test_poll_secs_outside_the_operational_range_is_refused(poll_secs: float) -> None:
    """A typo in a profile is found at config load, not during an incident."""
    with pytest.raises(ValidationError):
        HaltConfig(poll_secs=poll_secs)


def test_resolved_halt_trip_path_uses_the_runs_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trip file inherits ZERODTE_RUNS_DIR (D9), and so inherits the conftest tripwire."""
    monkeypatch.setenv("ZERODTE_RUNS_DIR", str(tmp_path / "env_runs"))
    config = AppConfig(trader_id="TRADER-007")
    assert config.resolved_halt_trip_path() == tmp_path / "env_runs" / "halt" / "TRADER-007.trip"


def test_resolved_halt_trip_path_explicit_arg_beats_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZERODTE_RUNS_DIR", str(tmp_path / "env_runs"))
    config = AppConfig(trader_id="TRADER-007")
    explicit = tmp_path / "explicit_runs"
    assert config.resolved_halt_trip_path(explicit) == explicit / "halt" / "TRADER-007.trip"


def test_resolved_halt_trip_path_falls_back_to_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the variable unset the base is the repo's runs/, same as the journal."""
    monkeypatch.delenv("ZERODTE_RUNS_DIR", raising=False)
    config = AppConfig(trader_id="TRADER-007")
    assert config.resolved_halt_trip_path() == Path("runs") / "halt" / "TRADER-007.trip"
