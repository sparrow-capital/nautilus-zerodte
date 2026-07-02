from __future__ import annotations

from nautilus_zerodte.config.schema import ApprovalConfig
from nautilus_zerodte.models.enums import ActorKind
from nautilus_zerodte.models.trade_intent import TradeIntent

ApprovalThresholds = ApprovalConfig


def classify_intent(intent: TradeIntent, thresholds: ApprovalConfig) -> ActorKind:
    """Route large or high-edge trades to human approval; otherwise automation."""
    if intent.edge_after_cost_bps >= thresholds.human_edge_bps_threshold:
        return ActorKind.HUMAN
    notional = intent.rationale.get("notional") or intent.rationale.get("net_debit")
    if notional is not None and float(notional) >= thresholds.human_notional_threshold:
        return ActorKind.HUMAN
    return ActorKind.AUTOMATION
