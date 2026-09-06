from __future__ import annotations

from nautilus_trader.adapters.deribit import DERIBIT

from nautilus_zerodte.config.schema import AppConfig
from nautilus_zerodte.models.enums import VenueAdapter
from nautilus_zerodte.node.adapters.registry import build_venue_client_wiring, resolve_venue_adapter


def test_resolve_venue_adapter_deribit() -> None:
    config = AppConfig(venue={"adapter": "DERIBIT"})
    assert resolve_venue_adapter(config) is VenueAdapter.DERIBIT


def test_resolve_venue_adapter_ib() -> None:
    config = AppConfig(venue={"adapter": "IB"})
    assert resolve_venue_adapter(config) is VenueAdapter.IB


def test_build_deribit_wiring_on_dry_run() -> None:
    config = AppConfig(
        venue={"adapter": "DERIBIT", "name": "DERIBIT"},
        deribit={"testnet": True},
    )
    wiring = build_venue_client_wiring(config, dry_run=True)

    assert DERIBIT in wiring.data_clients
    assert DERIBIT in wiring.exec_clients
    assert DERIBIT in wiring.data_client_factories
    assert DERIBIT in wiring.exec_client_factories
    wiring.data_clients[DERIBIT].json()
    wiring.exec_clients[DERIBIT].json()


def test_build_ib_wiring_skipped_on_dry_run() -> None:
    config = AppConfig(venue={"adapter": "IB"})
    wiring = build_venue_client_wiring(config, dry_run=True)

    assert not wiring.data_clients
    assert not wiring.exec_clients


def test_deribit_wiring_requests_the_combo_product_type() -> None:
    """The strategy trades a Deribit COMBO, so the adapter must be able to load one.

    `strategies/reference.py:submit_entry` looks the combo up with
    `self.cache.instrument(<combo id>)` and journals `instrument_not_found` when it is absent.
    `DeribitProductType` declares OPTION_COMBO, so omitting it from `product_types` means the
    instrument the strategy trades can never be provided - on either the data or the exec
    client. Asserted on both, because they are configured separately and only the data client
    has an `auto_load_missing_instruments` fallback.
    """
    config = AppConfig(
        venue={"adapter": "DERIBIT", "name": "DERIBIT"},
        deribit={"testnet": True},
    )
    wiring = build_venue_client_wiring(config, dry_run=True)

    for label, client in (
        ("data", wiring.data_clients[DERIBIT]),
        ("exec", wiring.exec_clients[DERIBIT]),
    ):
        product_types = tuple(str(p) for p in (client.product_types or ()))
        assert any("OPTION_COMBO" in p for p in product_types), (
            f"{label} client product_types={product_types} cannot load a combo instrument"
        )
        assert any(p.endswith("OPTION") or "OPTION'" in p for p in product_types), (
            f"{label} client must still load the option legs: {product_types}"
        )
