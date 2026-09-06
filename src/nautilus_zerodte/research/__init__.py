"""Offline research tooling. Never on the order path (T6).

Deliberately empty of imports. `offline.py` pulls in the trading engine, and re-exporting it
here made every module in this package - including ones with no engine dependency at all, such
as `combo_probe` - unimportable on a machine where nautilus-trader cannot be installed. That is
every Intel Mac, since no macOS x86_64 wheel is published for any version. Import submodules
directly: `from nautilus_zerodte.research.offline import run_catalog_partitions`.
"""
