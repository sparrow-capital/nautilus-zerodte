"""The state diagram must describe the state machine the code actually has.

`docs/design/state-diagram.puml` had been stale for months in a way nobody could see from the
picture: it omitted `PendingApproval` entirely, so the whole selector path - the one that exists
whenever more than one strategy runs - was simply absent. It also drew `InPosition -> Flat`
directly on the flatten signal, when the code goes `InPosition -> Exiting -> Flat`, and labelled
a `PendingEntry -> Flat` edge "cancelled", which is not a transition the code has.

A diagram is documentation of a control flow, and this project's standing lesson is that
documentation trusted without being checked is the dangerous kind. So the check is here rather
than in a reviewer's head.

Transition reasons are public API under hard rule 8, which is what makes pinning them fair: a
renamed reason is already a breaking change, so a test that notices one is not friction, it is
the notification.

The checks read the diagram's EDGES, not its text. The first version of this file asked
whether the state's name appeared anywhere in the file, and a mutation proved that vacuous:
deleting the only edge INTO `PendingApproval` still left the name in its own `state` block and
in two outbound edges, so the check passed on a diagram with an unreachable state - the precise
defect it was written to catch. A state you cannot get to is not in the diagram in any sense
that matters to a reader.

What this deliberately does NOT assert: that the diagram has no extra states or edges. Some
transitions pass their reason through from a caller (`flatten_positions(reason=...)`,
`_journal_order_error`) and are invisible to a static scan, so the diagram legitimately carries
labels this test cannot find. A floor, not an exact match.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from nautilus_zerodte.models.enums import StrategyState

REPO = Path(__file__).resolve().parents[2]
DIAGRAM = REPO / "docs" / "design" / "state-diagram.puml"
STRATEGIES = REPO / "src" / "nautilus_zerodte" / "strategies"


EDGE = re.compile(r"^\s*(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)\s*(?::\s*(.*))?$")


def _edges() -> list[tuple[str, str, str]]:
    """(source, target, label) for every transition line, ignoring notes and state bodies.

    Reading edges rather than raw text is the point: a name mentioned only inside a `state`
    block or a note tells a reader nothing about how the machine gets there.
    """
    edges: list[tuple[str, str, str]] = []
    for line in DIAGRAM.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("'"):
            continue
        match = EDGE.match(line)
        if match:
            edges.append((match.group(1), match.group(2), match.group(3) or ""))
    return edges


def _literal_transition_reasons() -> dict[str, str]:
    """Every `self._transition(..., reason="literal")` in strategies/, mapped to its module.

    Only literals. A reason forwarded from a parameter cannot be known statically, and
    pretending otherwise would make this test assert something it cannot see.
    """
    found: dict[str, str] = {}
    for module in sorted(STRATEGIES.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "_transition":
                continue
            for keyword in node.keywords:
                if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, str):
                        found[keyword.value.value] = module.name
    return found


def test_the_scan_found_the_diagram_and_the_transitions() -> None:
    """Guard the guard: an empty scan would make both real checks vacuously true."""
    assert DIAGRAM.exists(), f"state diagram not found at {DIAGRAM}"
    edges = _edges()
    assert len(edges) >= 10, f"parsed only {len(edges)} edges from {DIAGRAM}: {edges}"
    reasons = _literal_transition_reasons()
    assert len(reasons) >= 10, (
        f"found only {len(reasons)} literal transition reasons under {STRATEGIES}: "
        f"{sorted(reasons)}. The AST scan is wrong, not the source."
    )


def test_every_strategy_state_is_reachable_and_leaveable_in_the_diagram() -> None:
    """Every state needs an edge in and an edge out, or a reader cannot trace the machine."""
    edges = _edges()
    inbound = {target for _, target, _ in edges}
    outbound = {source for source, _, _ in edges}
    broken = {
        state.value: [
            side
            for side, present in (
                ("no edge in", state.value in inbound),
                ("no edge out", state.value in outbound),
            )
            if not present
        ]
        for state in StrategyState
    }
    broken = {state: sides for state, sides in broken.items() if sides}
    assert not broken, (
        "states in StrategyState that the diagram does not connect: "
        f"{broken}.\nA state named in a block or a note but with no edge is unreachable on the "
        "picture, which hides a whole path. Add the edges, then re-render the PNG."
    )


def test_every_literal_transition_reason_appears_in_the_diagram() -> None:
    """Transition reasons are public API (hard rule 8), so the diagram must carry them."""
    labels = " | ".join(label for _, _, label in _edges())
    missing = {
        reason: module
        for reason, module in _literal_transition_reasons().items()
        if not re.search(rf"(?<![\w-]){re.escape(reason)}(?![\w-])", labels)
    }
    assert not missing, (
        "transition reasons recorded by the code but absent from the state diagram:\n  "
        + "\n  ".join(
            f"{reason} (strategies/{module})" for reason, module in sorted(missing.items())
        )
        + "\n\nChecked against EDGE LABELS only, not the whole file, so a reason mentioned in "
        "a note does not count. Either the diagram is stale or the reason is new; both need the "
        "diagram edited and the PNG re-rendered."
    )


def test_the_rendered_png_is_present() -> None:
    """The PNG is what people actually look at; a source-only change leaves them the old one."""
    png = DIAGRAM.with_suffix(".png")
    assert png.exists(), f"{png} missing - re-render with the plantuml image, see docs/design/"
    assert png.stat().st_size > 1000, f"{png} is suspiciously small at {png.stat().st_size} bytes"
