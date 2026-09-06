from __future__ import annotations

from pathlib import Path

from nautilus_zerodte.research.offline import _quote_tick_count, list_quote_tick_partitions


def test_list_quote_tick_partitions_on_spy_fixture() -> None:
    catalog = Path("tests/fixtures/catalog")
    partitions = list_quote_tick_partitions(catalog)
    assert "SPY.NYSE" in partitions


def test_quote_tick_count_worker_on_spy_fixture() -> None:
    catalog = Path("tests/fixtures/catalog")
    result = _quote_tick_count((str(catalog), "SPY.NYSE"))
    assert result["instrument_id"] == "SPY.NYSE"
    assert result["quote_tick_count"] > 0


def test_research_package_init_does_not_import_the_engine() -> None:
    """`research/` must import without nautilus-trader present.

    It is offline diagnostic tooling, and some of it (combo_probe) has no engine dependency at
    all - but a re-export in __init__.py made the whole package need one, which broke running a
    probe on any machine that cannot install the engine. Parsed rather than grepped: the first
    version of this test searched for the string "nautilus_trader" and failed on its own
    docstring. Static, because in CI the engine IS installed, so an import test could not fail.
    """
    import ast
    from pathlib import Path

    init = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "nautilus_zerodte"
        / "research"
        / "__init__.py"
    )
    tree = ast.parse(init.read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)]
    assert not imports, (
        "research/__init__.py must stay import-free so submodules with no engine dependency "
        f"remain importable without nautilus-trader; found {len(imports)}"
    )
