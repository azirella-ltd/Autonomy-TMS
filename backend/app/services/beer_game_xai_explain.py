"""Plain-English decision explanations for Autonomy temporal-GNN agents.

This module is adapted from the provided specification to generate
consistent natural-language rationales for both decentralized Autonomy
agents and the optional centralized supervisor.  It purposefully avoids
heavy dependencies so that explanations can be computed anywhere in the
stack (training, serving, or offline analysis).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Sequence
import math


# ---------- Data containers ----------


@dataclass
class Obs:
    on_hand: int
    backlog: int
    pipeline_orders: Sequence[int]  # orders the node placed that have not yet arrived (by week 1..L)
    pipeline_shipments: Sequence[int]  # shipments known inbound but not received yet (by week 1..L)
    last_k_orders_in: Sequence[int] = field(default_factory=list)  # recent downstream orders received
    last_k_shipments_in: Sequence[int] = field(default_factory=list)
    last_k_orders_out: Sequence[int] = field(default_factory=list)
    capacity_flag: Optional[bool] = None
    notes: Optional[str] = None  # any freeform context

    def inventory_position(self) -> int:
        return int(self.on_hand + sum(self.pipeline_shipments) - self.backlog)


@dataclass
class Forecast:
    """Temporal-GNN forecast, per-role local view only.
    Provide either horizon sums or per-week vectors (we auto-aggregate over lead time).
    """

    mean: Sequence[float]  # length >= lead_time (per-week mean demand the node expects to fulfill)
    std: Optional[Sequence[float]] = None  # per-week std; if None, assume 0


@dataclass
class RoleParams:
    lead_time: int  # in weeks
    service_level: float = 0.95  # target cycle service level
    min_lot: Optional[int] = None
    capacity_cap: Optional[int] = None  # max order allowed
    smoothing_lambda: float = 0.0  # optional (order-change penalty in your RL reward)


@dataclass
class ActionContext:
    prev_action_qty: Optional[int] = None  # for smoothing commentary
    shadow_policy: str = "base_stock"  # or "none"; used for deterministic summary


@dataclass
class SupervisorContext:
    max_scale_pct: float  # e.g., 10 means supervisor can scale ±10%
    rule: str  # e.g., "stability_smoothing", "cost_hedging", "fill_rate_guardrail"
    reasons: List[str] = field(default_factory=list)


# ---------- Utilities ----------


# Conservative z-scores for common service levels (no SciPy dependency)
_Z_LOOKUP = {
    0.80: 0.8416,
    0.85: 1.0364,
    0.90: 1.2816,
    0.95: 1.6449,
    0.97: 1.8808,
    0.98: 2.0537,
    0.99: 2.3263,
}


def z_for_service(p: float) -> float:
    keys = sorted(_Z_LOOKUP.keys())
    if p in _Z_LOOKUP:
        return _Z_LOOKUP[p]
    # linear interpolate between nearest keys
    lo = max([k for k in keys if k <= p] or [min(keys)])
    hi = min([k for k in keys if k >= p] or [max(keys)])
    if lo == hi:
        return _Z_LOOKUP[lo]
    t = (p - lo) / (hi - lo)
    return _Z_LOOKUP[lo] * (1 - t) + _Z_LOOKUP[hi] * t


def aggregate_over_lead_time(arr: Sequence[float], L: int) -> float:
    if L <= 0:
        return 0.0
    if len(arr) < L:
        # pad conservatively with last value
        if not arr:
            return 0.0
        tail = [arr[-1]] * (L - len(arr))
        vals = list(arr) + tail
    else:
        vals = arr[:L]
    return float(sum(vals))


def lead_time_sigma(std_vec: Optional[Sequence[float]], L: int) -> float:
    if not std_vec or L <= 0:
        return 0.0
    # assume independence across weeks for simplicity; replace with covariance if available
    vals = std_vec[:L] if len(std_vec) >= L else list(std_vec) + [std_vec[-1]] * (L - len(std_vec))
    var = sum(s ** 2 for s in vals)
    return math.sqrt(var)


def base_stock_target(forecast: Forecast, params: RoleParams) -> Tuple[float, float, float]:
    """Return (S_target, mu_L, sigma_L).
    S = E[LTD] + z * sigma_L
    """

    L = int(params.lead_time)
    mu_L = aggregate_over_lead_time(forecast.mean, L)
    sigma_L = lead_time_sigma(forecast.std, L)
    z = z_for_service(params.service_level)
    S = mu_L + z * sigma_L
    return S, mu_L, sigma_L


def clamp_capacity_and_lot(q: int, params: RoleParams) -> int:
    if params.capacity_cap is not None:
        q = min(q, int(params.capacity_cap))
    if params.min_lot:
        lot = int(params.min_lot)
        if lot > 0:
            # round up to satisfy minimum lot (or nearest multiple)? Here: round to nearest >= 1 lot
            q = lot * max(1, int(round(q / lot)))
    return max(0, int(q))


# ---------- Explanations ----------


def rank_top_drivers(driver_scores: Dict[str, float], k: int = 5) -> List[Tuple[str, float]]:
    if not driver_scores:
        return []
    return sorted(driver_scores.items(), key=lambda kv: abs(kv[1]), reverse=True)[:k]


def _fmt_pct(x: float) -> str:
    return f"{x:.0%}" if abs(x) >= 0.01 else f"{x*100:.1f}%"


def explain_role_decision(
    role: str,
    week: int,
    obs: Obs,
    action_qty: int,
    forecast: Optional[Forecast],
    params: RoleParams,
    shadow_policy: str = "base_stock",
    actor_attribution: Optional[Dict[str, float]] = None,
    whatif_cfg: Optional[Dict[str, float]] = None,
    prev_action_qty: Optional[int] = None,
) -> str:
    """Produce a plain-English rationale for a role's order decision.

    Visibility: this uses only local observables + the (possibly supervisor-provided) local forecast.
    """

    ip = obs.inventory_position()

    # Deterministic shadow computation (if requested)
    det_bits = []
    target_S = None
    mu_L = sigma_L = None
    if shadow_policy == "base_stock" and forecast is not None:
        target_S, mu_L, sigma_L = base_stock_target(forecast, params)
        gap = target_S - ip
        det_bits.append(
            f"Target ≈ {round(target_S)} (lead-time demand μ={mu_L:.1f} ± {sigma_L:.1f}, service={int(params.service_level*100)}%)."
        )
        det_bits.append(f"Inventory position IP={ip}; gap to target ≈ {round(gap)}.")

    # Constraints and post-processing applied to the chosen action (for auditing only)
    constrained_action = clamp_capacity_and_lot(action_qty, params)
    capacity_note = None
    if params.capacity_cap is not None and action_qty > params.capacity_cap:
        capacity_note = f"capacity cap {params.capacity_cap} applied"
    lot_note = None
    if params.min_lot:
        lot_note = f"min lot {params.min_lot} enforced"

    # Attribution / drivers
    top_drivers = rank_top_drivers(actor_attribution or {}, k=5)

    # What-ifs (local, small deltas)
    what_ifs = []
    if whatif_cfg and forecast is not None:
        # Demand scale counterfactual
        if "demand_scale" in whatif_cfg:
            scale = float(whatif_cfg["demand_scale"])  # e.g., 0.8 or 1.2
            mu_cf = aggregate_over_lead_time([m * scale for m in forecast.mean], params.lead_time)
            sigma_cf = lead_time_sigma(forecast.std, params.lead_time)
            S_cf = mu_cf + z_for_service(params.service_level) * sigma_cf
            gap_cf = S_cf - ip
            q_cf = clamp_capacity_and_lot(max(0, round(gap_cf)), params)
            delta = q_cf - constrained_action
            sign = "+" if delta >= 0 else ""
            what_ifs.append(
                f"If next {params.lead_time}w demand were {int((scale-1)*100)}% different, I would order {sign}{delta} units."
            )
        # Lead time delta counterfactual
        if "lead_time_delta" in whatif_cfg and forecast is not None:
            dL = int(whatif_cfg["lead_time_delta"])  # e.g., -1 or +1
            L_cf = max(0, params.lead_time + dL)
            mu_cf = aggregate_over_lead_time(forecast.mean, L_cf)
            sigma_cf = lead_time_sigma(forecast.std, L_cf)
            S_cf = mu_cf + z_for_service(params.service_level) * sigma_cf
            gap_cf = S_cf - ip
            q_cf = clamp_capacity_and_lot(max(0, round(gap_cf)), params)
            delta = q_cf - constrained_action
            sign = "+" if delta >= 0 else ""
            what_ifs.append(
                f"If lead time were {dL:+d}w (to {L_cf}w), I would order {sign}{delta} units."
            )

    # Build the natural-language explanation
    lines = []
    lines.append(f"Decision (Week {week}, {role}): order **{constrained_action}** units upstream.")
    lines.append(
        f"Why: IP={ip} (on-hand {obs.on_hand}, pipeline-in {sum(obs.pipeline_shipments)}, backlog {obs.backlog}). Lead time {params.lead_time}w."
    )
    if det_bits:
        lines.extend(det_bits)
        # how far from shadow policy is the chosen action?
        if target_S is not None:
            gap = round(target_S - ip)
            naive = clamp_capacity_and_lot(max(0, gap), params)
            delta_vs_shadow = constrained_action - naive
            if abs(delta_vs_shadow) <= 1:
                lines.append("Action ~ matches base-stock target.")
            else:
                sign = "+" if delta_vs_shadow > 0 else ""
                lines.append(
                    f"Action is {sign}{delta_vs_shadow} vs. naïve base-stock, accounting for smoothing/caps."
                )
    if params.capacity_cap is not None or params.min_lot:
        cap_bits = [b for b in [capacity_note, lot_note] if b]
        if cap_bits:
            lines.append("Constraints: " + ", ".join(cap_bits) + ".")
    if prev_action_qty is not None and params.smoothing_lambda > 0:
        delta = constrained_action - prev_action_qty
        lines.append(
            f"Smoothing: changed by {delta:+d} from last week ({prev_action_qty})."
        )

    if top_drivers:
        lines.append("Top signals influencing this choice:")
        for name, score in top_drivers:
            sign = "+" if score >= 0 else ""
            lines.append(f"• {name} ({sign}{score:.2f})")

    if what_ifs:
        lines.append("What-ifs:")
        for w in what_ifs:
            lines.append(f"• {w}")

    return "\n".join(lines)


def explain_supervisor_adjustment(
    role: str,
    week: int,
    pre_qty: int,
    post_qty: int,
    ctx: SupervisorContext,
    global_notes: Optional[List[str]] = None,
) -> str:
    """Explain the Supervisor's scaling of a role's order within ±max_scale_pct.

    This should be emitted *in addition* to the role's own explanation, and should
    be clearly labeled as a global override.
    """

    if pre_qty == 0:
        scale_pct = 0.0 if post_qty == 0 else 1.0
    else:
        scale_pct = (post_qty - pre_qty) / pre_qty
    bounded = abs(scale_pct) <= (ctx.max_scale_pct / 100 + 1e-9)
    lines = []
    lines.append(
        f"Supervisor (Week {week}) adjusted {role}'s order from {pre_qty} → {post_qty} ({_fmt_pct(scale_pct)})."
    )
    lines.append(f"Rule: {ctx.rule}. Limit: ±{ctx.max_scale_pct:.0f}% ⇒ {'OK' if bounded else 'EXCEEDED!'}.")
    if ctx.reasons:
        lines.append("Reasons: " + "; ".join(ctx.reasons) + ".")
    if global_notes:
        lines.append("Global context: " + "; ".join(global_notes) + ".")
    return "\n".join(lines)


# ---------- Optional helpers for logging & evaluation ----------


@dataclass
class DecisionLog:
    week: int
    role: str
    action_qty: int
    explanation: str


def log_explanations(decisions: List[DecisionLog]) -> str:
    """Join multiple explanations with separators (nice for episode summaries)."""

    sep = "\n" + ("-" * 72) + "\n"
    return sep.join([d.explanation for d in decisions])


# ---------- Example (doctest-style) ----------


if __name__ == "__main__":
    obs = Obs(
        on_hand=30,
        backlog=8,
        pipeline_orders=[12, 12],
        pipeline_shipments=[10, 10],
        last_k_orders_in=[24, 28],
        last_k_shipments_in=[20, 18],
    )
    fcst = Forecast(mean=[28, 32, 30], std=[6, 7, 6])
    params = RoleParams(lead_time=2, service_level=0.95, min_lot=12)

    txt = explain_role_decision(
        role="Wholesaler",
        week=7,
        obs=obs,
        action_qty=36,
        forecast=fcst,
        params=params,
        shadow_policy="base_stock",
        actor_attribution={"backlog_growth(2w)": 0.32, "recv_ship_t-1": 0.27, "fcst_sigma": 0.18},
        whatif_cfg={"lead_time_delta": -1, "demand_scale": 0.8},
        prev_action_qty=30,
    )
    print(txt)

    sup = explain_supervisor_adjustment(
        role="Wholesaler",
        week=7,
        pre_qty=36,
        post_qty=39,
        ctx=SupervisorContext(max_scale_pct=10, rule="stability_smoothing",
                              reasons=["upstream backlog rising", "manufacturer idle capacity"]),
    )
    print("\n" + sup)
