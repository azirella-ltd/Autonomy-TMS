"""Reusable helpers for supply chain simulation state updates."""

from typing import Any, Dict, List, Tuple


from typing import Any, Dict, List, Optional, Tuple


def snapshot_queue(values: Any) -> List[int]:
    if values is None:
        return []
    if isinstance(values, list):
        iterable = values
    elif isinstance(values, tuple):
        iterable = list(values)
    elif isinstance(values, set):
        iterable = list(values)
    elif hasattr(values, "__iter__") and not isinstance(values, (str, bytes)):
        try:
            iterable = list(values)
        except TypeError:
            iterable = [values]
    else:
        iterable = [values]
    snapshot: List[int] = []
    for item in iterable:
        try:
            snapshot.append(int(item))
        except (TypeError, ValueError):
            continue
    return snapshot


def snapshot_detail_queue(values: Any) -> List[Dict[str, Dict[str, int]]]:
    if not isinstance(values, list):
        return []
    detail_snapshot: List[Dict[str, Dict[str, int]]] = []
    for entry in values:
        if isinstance(entry, dict):
            bucket: Dict[str, Dict[str, int]] = {}
            for downstream, payload in entry.items():
                if isinstance(payload, dict):
                    item_map: Dict[str, int] = {}
                    for item, qty in payload.items():
                        if isinstance(qty, (int, float)):
                            qty_val = int(qty)
                            if qty_val > 0:
                                item_map[str(item)] = item_map.get(str(item), 0) + qty_val
                    if item_map:
                        bucket[str(downstream)] = item_map
                elif isinstance(payload, (int, float)):
                    # Require an explicit item id; surface an error so upstream generation can be fixed.
                    raise ValueError("Queue detail entry is missing an explicit product_id")
            detail_snapshot.append(bucket)
        else:
            detail_snapshot.append({})
    return detail_snapshot


def ensure_queue_length(queue: List[int], length: int) -> List[int]:
    if length <= 0:
        return []
    if not isinstance(queue, list):
        queue = []
    queue = [int(x) for x in queue if isinstance(x, (int, float))]
    if len(queue) < length:
        queue = [0] * (length - len(queue)) + queue
    elif len(queue) > length:
        queue = queue[-length:]
    return queue


def ensure_detail_queue(
    queue: List[Dict[str, Any]], length: int
) -> List[Dict[str, Dict[str, int]]]:
    if length <= 0:
        return []
    detail = snapshot_detail_queue(queue)
    while len(detail) < length:
        detail.insert(0, {})
    if len(detail) > length:
        detail = detail[-length:]
    return detail


def _coerce_step(value: Any, default: int) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_inbound_supply_queue(
    queue: Any,
    *,
    current_step: int,
    fallback: Optional[List[int]] = None,
    supply_leadtime: int = 0,
) -> List[Dict[str, Any]]:
    """Return a normalised inbound supply queue with explicit step numbers."""

    entries: List[Dict[str, Any]] = []
    if isinstance(queue, list):
        if not queue:
            return []
        is_dict_queue = any(isinstance(x, dict) for x in queue)
        if not is_dict_queue:
            raise ValueError(
                "Inbound supply queue must be a list of dict entries containing product_id, source, step_number, and quantity"
            )
        for raw in queue:
            if not isinstance(raw, dict):
                continue
            step_raw = raw.get("step_number") or raw.get("arrival_round") or raw.get("due_round") or raw.get("step")
            try:
                step_number = int(step_raw)
            except (TypeError, ValueError):
                continue
            qty_raw = raw.get("quantity") or raw.get("qty")
            try:
                quantity = int(qty_raw)
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue
            source = raw.get("source") or raw.get("from") or raw.get("upstream")
            if source is None:
                raise ValueError(f"Inbound supply entry missing source: {raw}")
            product_id = raw.get("product_id") or raw.get("item_id") or raw.get("item") or raw.get("sku")
            if product_id is None:
                raise ValueError(f"Inbound supply entry missing product_id: {raw}")
            entries.append(
                {
                    "step_number": step_number,
                    "quantity": quantity,
                    "source": str(source),
                    "product_id": str(product_id),
                }
            )

    if not entries and isinstance(fallback, list):
        if any(isinstance(x, dict) for x in fallback):
            for raw in fallback:
                if not isinstance(raw, dict):
                    continue
                step_raw = raw.get("step_number") or raw.get("arrival_round") or raw.get("due_round") or raw.get("step")
                try:
                    step_number = int(step_raw)
                except (TypeError, ValueError):
                    continue
                qty_raw = raw.get("quantity") or raw.get("qty")
                try:
                    quantity = int(qty_raw)
                except (TypeError, ValueError):
                    continue
                if quantity <= 0:
                    continue
                product_id = raw.get("product_id") or raw.get("item_id") or raw.get("item") or raw.get("sku")
                if product_id is None:
                    raise ValueError(f"Fallback inbound supply entry missing product_id: {raw}")
                source = raw.get("source") or raw.get("from") or raw.get("upstream")
                if source is None:
                    raise ValueError(f"Fallback inbound supply entry missing source: {raw}")
                entries.append(
                    {
                        "step_number": step_number,
                        "quantity": quantity,
                        "product_id": str(product_id),
                        "source": str(source),
                    }
                )
        else:
            raise ValueError("Fallback inbound supply queue provided without product_id data")

    entries.sort(key=lambda item: item.get("step_number", current_step))
    return entries


def sort_inbound_supply_queue(queue: List[Dict[str, Any]]) -> None:
    queue.sort(key=lambda item: item.get("step_number", 0))


def partition_inbound_supply_queue(
    queue: List[Dict[str, Any]], *, current_step: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    due: List[Dict[str, Any]] = []
    future: List[Dict[str, Any]] = []
    for entry in queue:
        step_number = _coerce_step(entry.get("step_number"), current_step)
        normalised = {
            "step_number": step_number,
            "quantity": int(entry.get("quantity", 0) or 0),
        }
        if "source" in entry:
            normalised["source"] = entry["source"]
        if "product_id" in entry:
            normalised["product_id"] = entry["product_id"]
        if normalised["quantity"] <= 0:
            continue
        if step_number <= current_step:
            due.append(normalised)
        else:
            future.append(normalised)
    sort_inbound_supply_queue(future)
    return due, future


def summarise_inbound_supply_queue(
    queue: List[Dict[str, Any]], *, current_step: int, supply_leadtime: int
) -> List[int]:
    if not queue:
        return [0] * max(supply_leadtime, 0)
    offsets = [
        max(0, int(entry.get("step_number", current_step)) - current_step)
        for entry in queue
    ]
    max_offset = max(offsets + [supply_leadtime])
    if max_offset <= 0:
        return [0] * max(supply_leadtime, 0)
    buckets = [0] * max_offset
    for entry in queue:
        try:
            step_number = int(entry.get("step_number", current_step))
            quantity = int(entry.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        offset = step_number - current_step
        if offset <= 0:
            continue
        idx = offset - 1
        if idx < 0:
            continue
        if idx >= len(buckets):
            buckets.extend([0] * (idx + 1 - len(buckets)))
        buckets[idx] += quantity
    return buckets


def summarise_inbound_supply_detail(
    queue: List[Dict[str, Any]], *, current_step: int, supply_leadtime: int
) -> List[Dict[str, Dict[str, int]]]:
    if not queue:
        return [{} for _ in range(max(supply_leadtime, 0))]

    offsets = [
        max(0, int(entry.get("step_number", current_step)) - current_step)
        for entry in queue
    ]
    max_offset = max(offsets + [supply_leadtime])
    if max_offset <= 0:
        return [{} for _ in range(max(supply_leadtime, 0))]

    buckets: List[Dict[str, Dict[str, int]]] = [{} for _ in range(max_offset)]
    for entry in queue:
        try:
            step_number = int(entry.get("step_number", current_step))
            quantity = int(entry.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        offset = step_number - current_step
        if offset <= 0:
            continue
        idx = offset - 1
        if idx < 0:
            continue
        if idx >= len(buckets):
            buckets.extend({} for _ in range(idx + 1 - len(buckets)))
        bucket = buckets[idx]
        source = entry.get("source") or entry.get("from") or entry.get("upstream")
        product_id = entry.get("product_id") or entry.get("item_id") or entry.get("item") or entry.get("sku")
        source_key = str(source) if source is not None else "__upstream__"
        if product_id is None:
            raise ValueError("Inbound supply entry is missing an explicit product_id")
        item_key = str(product_id)
        item_map = bucket.setdefault(source_key, {})
        item_map[item_key] = item_map.get(item_key, 0) + quantity

    return [
        {downstream: dict(items) for downstream, items in bucket.items()}
        for bucket in buckets
    ]


def process_ship_queue(
    state_node: Dict[str, Any],
    policy: Dict[str, Any],
    *,
    current_step: Optional[int] = None,
) -> Tuple[int, List[int]]:
    """Advance a node's shipment pipeline and return the arrival quantity."""

    supply_leadtime = max(0, int(policy.get("supply_leadtime", 0)))
    if current_step is None:
        current_step = int(state_node.get("current_step", 0))
    else:
        try:
            current_step = int(current_step)
        except (TypeError, ValueError):
            current_step = int(state_node.get("current_step", 0))

    fallback_entries: Optional[List[Dict[str, Any]]] = None
    raw_fallback = state_node.get("ship_queue")
    if isinstance(raw_fallback, list) and raw_fallback:
        if all(isinstance(x, dict) for x in raw_fallback):
            fallback_entries = raw_fallback
        elif all(isinstance(x, (int, float)) for x in raw_fallback):
            item_candidates = state_node.get("inventory_by_item") or state_node.get("base_stock_by_item") or {}
            item_token = next(iter(item_candidates.keys()), None)
            if item_token is None:
                raise ValueError("Ship queue lacks product_id and no inventory item is available to infer one")
            fallback_entries = [
                {"step_number": current_step + idx + 1, "quantity": int(val), "product_id": item_token}
                for idx, val in enumerate(raw_fallback)
                if isinstance(val, (int, float)) and int(val) > 0
            ]

    arrivals_queue = normalize_inbound_supply_queue(
        state_node.get("inbound_supply_future"),
        current_step=current_step,
        fallback=fallback_entries,
        supply_leadtime=supply_leadtime,
    )

    due_now, future_queue = partition_inbound_supply_queue(arrivals_queue, current_step=current_step)
    arriving = sum(entry.get("quantity", 0) for entry in due_now)

    sort_inbound_supply_queue(future_queue)
    state_node["inbound_supply_future"] = future_queue
    state_node["current_step"] = current_step

    snapshot = summarise_inbound_supply_queue(
        future_queue,
        current_step=current_step,
        supply_leadtime=supply_leadtime,
    )

    if supply_leadtime > 0:
        state_node["ship_queue"] = list(snapshot)
    else:
        state_node["ship_queue"] = []

    detail_snapshot = summarise_inbound_supply_detail(
        future_queue,
        current_step=current_step,
        supply_leadtime=supply_leadtime,
    )
    state_node["ship_detail_queue"] = detail_snapshot
    state_node["incoming_shipments"] = list(snapshot)
    return int(arriving), list(snapshot)


def compute_shipping_outcome(
    *,
    node_type: str,
    inventory_before: int,
    backlog_before: int,
    arrivals_now: int,
    incoming_now: int,
) -> Tuple[int, int, int, int, int]:
    """Resolve local shipping given supply, demand, and node type."""

    demand_now = backlog_before + incoming_now
    available_now = inventory_before + arrivals_now

    if node_type == "vendor":
        shipped_now = demand_now
        inventory_after = max(0, available_now - shipped_now)
        backlog_after = 0
    else:
        shipped_now = min(available_now, demand_now)
        inventory_after = available_now - shipped_now
        backlog_after = demand_now - shipped_now

    return shipped_now, inventory_after, backlog_after, demand_now, available_now
