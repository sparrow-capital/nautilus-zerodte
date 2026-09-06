"""Machine-check the guardrail table in `docs/quant/risk.md`.

That table opens with "Every row needs a test that trips it. A limit with no test does not
exist." It was prose, so it was not true: rows named a "Risk actor" that has never existed in
`src/`, and the table read as a description of controls rather than a wish list.

This makes the claim enforceable. Each row's "Trip test" cell must either name a test that is
genuinely present in the suite, or say NOT IMPLEMENTED. A row cannot quietly claim coverage it
does not have, and the only way to move a row off NOT IMPLEMENTED is to name a test that really
exists.

Deliberately NOT asserted here: that the named test actually trips the guardrail. Nothing
static can know that, and pretending otherwise would be the same failure one level up. What
this catches is the drift that already happened - a table describing intent as if it were
enforcement.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RISK_MD = REPO_ROOT / "docs" / "quant" / "risk.md"
NOT_IMPLEMENTED = "NOT IMPLEMENTED"

# `tests/unit/test_gates.py::test_check_risk_policy_wrapper`, backticks optional.
_TEST_REF = re.compile(r"`?(?P<path>tests/[\w/]+\.py)::(?P<name>test_\w+)`?")


def _guardrail_rows() -> list[tuple[str, str]]:
    """(guardrail, trip-test cell) for every row of the section 1 table."""
    lines = RISK_MD.read_text(encoding="utf-8").splitlines()
    rows: list[tuple[str, str]] = []
    in_table = False
    for line in lines:
        if line.startswith("| Guardrail |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4 or set(cells[0]) <= {"-", " "}:
                continue
            rows.append((cells[0], cells[3]))
    return rows


def test_the_guardrail_table_was_found_and_is_not_empty() -> None:
    """Guard the guard: a parser that silently matches nothing would pass every other test.

    Doorway's P6 - refuse an empty table, because a zeroed table registers zero checks and
    reads green. The floor is a floor, not an exact count: adding a guardrail must be free.
    """
    rows = _guardrail_rows()
    assert len(rows) >= 10, f"parsed only {len(rows)} guardrail rows from {RISK_MD}"
    assert any("kill switch" in name.lower() for name, _ in rows)


def test_every_guardrail_names_a_real_trip_test_or_admits_it_has_none() -> None:
    unknown: list[str] = []
    for guardrail, cell in _guardrail_rows():
        if NOT_IMPLEMENTED in cell:
            continue
        match = _TEST_REF.search(cell)
        if match is None:
            unknown.append(
                f"{guardrail!r}: trip-test cell {cell!r} is neither a test id nor {NOT_IMPLEMENTED}"
            )
            continue
        path = REPO_ROOT / match.group("path")
        if not path.exists():
            unknown.append(f"{guardrail!r}: names {match.group('path')}, which does not exist")
            continue
        if f"def {match.group('name')}(" not in path.read_text(encoding="utf-8"):
            unknown.append(f"{guardrail!r}: {match.group('path')} has no {match.group('name')}")
    assert not unknown, "guardrail table claims coverage it does not have:\n  " + "\n  ".join(
        unknown
    )


def test_a_guardrail_claiming_a_missing_test_is_caught() -> None:
    """The check above can only be trusted if it fails on a fabricated claim.

    Runs the same validation over an invented row rather than mutating the real file, so the
    check is proven without a test that edits repository state.
    """
    fabricated = "`tests/unit/test_gates.py::test_this_does_not_exist`"
    match = _TEST_REF.search(fabricated)
    assert match is not None
    path = REPO_ROOT / match.group("path")
    assert path.exists(), "fixture assumes this file is real"
    assert f"def {match.group('name')}(" not in path.read_text(encoding="utf-8")
