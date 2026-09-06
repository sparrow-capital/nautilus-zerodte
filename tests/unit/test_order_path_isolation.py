"""T6 as enforcement rather than convention: nothing on the order path may import research.

`CLAUDE.md` T6 says the order path "never touches disk or network synchronously, never takes a
contended lock, and never runs research code", and `research/offline.py` says in its own
docstring that its process pool runs "never on the order path". Both were prose. Nothing stopped
a strategy from importing `research` and pulling a `ProcessPoolExecutor` and parquet reads into
a market-data callback.

The trap is concrete and close. `short_legs_first` - the short-leg-first unwind ordering that
D12 makes a hard rule - currently lives in `research/combo_probe.py`, because that is where it
was first needed. Whoever implements the flatten (ZR-12/H3) will reach for it, import
`research`, and violate T6 without noticing. This test stops that at the point of the mistake
and says why, instead of the ordering rule quietly arriving with a process pool attached.

Scope is `strategies/`, `gates/` and `actors/` - the packages whose code runs inside engine
callbacks. `cli/` and `node/` legitimately invoke research (the `research catalog` command,
node construction), and they are setup, not the hot path.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "nautilus_zerodte"
ORDER_PATH_PACKAGES = ("strategies", "gates", "actors")
FORBIDDEN_ROOT = "nautilus_zerodte.research"


def _order_path_modules() -> list[Path]:
    return sorted(path for package in ORDER_PATH_PACKAGES for path in (SRC / package).rglob("*.py"))


def _imports(module: Path) -> list[str]:
    """Every module named by an import in this file, at any nesting depth."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_the_order_path_packages_were_actually_found() -> None:
    """Guard the guard: an empty file list would make the real check vacuous."""
    modules = _order_path_modules()
    assert len(modules) >= 10, f"found only {len(modules)} order-path modules under {SRC}"
    found = {path.parent.name for path in modules}
    for package in ORDER_PATH_PACKAGES:
        assert package in found or any(package in str(p) for p in modules), (
            f"no modules found for {package}/ - the glob is wrong, not the source"
        )


def test_order_path_does_not_import_research() -> None:
    """A strategy, gate or actor importing research pulls a process pool into a callback."""
    violations = [
        f"{module.relative_to(SRC)} imports {name}"
        for module in _order_path_modules()
        for name in _imports(module)
        if name.startswith(FORBIDDEN_ROOT)
    ]
    assert not violations, (
        "T6: the order path must not import research code.\n  "
        + "\n  ".join(violations)
        + f"\n\nIf you need something from research/ (for example `short_legs_first`), move the "
        f"pure helper somewhere neither package owns rather than importing {FORBIDDEN_ROOT}."
    )


def test_the_import_scan_sees_nested_and_aliased_imports() -> None:
    """The check is only worth having if its parser catches the shapes people actually write.

    A regex over 'import research' would miss a function-level import, which is exactly how
    this violation would arrive - someone adds it inside the flatten method, not at module top.
    """
    sample = (
        "import os\n"
        "def flatten():\n"
        "    from nautilus_zerodte.research.combo_probe import short_legs_first\n"
        "    return short_legs_first\n"
    )
    tree = ast.parse(sample)
    names = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert any(name.startswith(FORBIDDEN_ROOT) for name in names), (
        "the scan must see imports nested inside a function body"
    )
