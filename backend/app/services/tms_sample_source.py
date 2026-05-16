"""TMS-side concrete :class:`SampleSource` — §3.57 Phase D.

Implements Core's
:class:`azirella_data_model.master.capacity_observed.SampleSource`
Protocol against TMS-owned historical-record tables:

  * ``otif_samples`` — read from ``outbound_order_line`` (which
    canonical Core owns; TMS reads through it). Each line with both
    ``ordered_quantity`` + ``shipped_quantity`` + a
    ``promised_delivery_date`` + ``last_ship_date`` (or
    ``first_ship_date`` when ``last_`` is null) contributes one
    :class:`OtifSample`.

  * ``throughput_samples`` — STUB. Throughput is SCP-domain
    (production_orders); not TMS's responsibility. Returns ``[]``
    so the 4-layer chain falls through to industry-default.

  * ``fulfilment_samples`` — STUB. Supplier-side fulfilment is
    SCP-domain (inbound_order_line + goods_receipt). Returns ``[]``.

Wiring (lifespan-time): a single :class:`TmsSampleSource` instance is
constructed at backend startup and handed to Core's
``StatisticalObservationProvider``. The 4-layer chain composer
(Core's ``ComposedDefaultProvider``) consults this source for the
observed-derived OTIF layer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from azirella_data_model.master.capacity_observed import (
    FulfilmentSample,
    OtifSample,
    SampleSource,
    ThroughputSample,
)

log = logging.getLogger(__name__)


class TmsSampleSource:
    """TMS-side :class:`SampleSource` implementation.

    Stateless. Queries are scoped by (tenant_id, config_id,
    customer_id) + a lookback window.
    """

    def throughput_samples(
        self,
        db: Session,
        *,
        tenant_id: int,
        config_id: int,
        site_id: int,
        work_center_code: str,
        lookback_days: int = 90,
    ) -> List[ThroughputSample]:
        """STUB: throughput is SCP-domain (production_orders),
        not TMS's responsibility. Returning empty falls through to
        SCP's SampleSource via the 4-layer chain composer, or
        industry-default when SCP isn't licensed."""
        log.debug(
            "TmsSampleSource.throughput_samples: STUB returning [] "
            "(SCP-domain; falls through to ScpSampleSource or "
            "industry_default)"
        )
        return []

    def fulfilment_samples(
        self,
        db: Session,
        *,
        tenant_id: int,
        config_id: int,
        supplier_id: str,
        product_id: Optional[str] = None,
        lookback_days: int = 90,
    ) -> List[FulfilmentSample]:
        """STUB: supplier-side fulfilment is SCP-domain
        (inbound_order_line + goods_receipt). Returns empty."""
        log.debug(
            "TmsSampleSource.fulfilment_samples: STUB returning [] "
            "(SCP-domain)"
        )
        return []

    def otif_samples(
        self,
        db: Session,
        *,
        tenant_id: int,
        config_id: int,
        customer_id: str,
        product_id: Optional[str] = None,
        lookback_days: int = 90,
    ) -> List[OtifSample]:
        """OTIF samples from realised outbound orders.

        Read every ``outbound_order_line`` for the
        (tenant, config, customer) whose ``last_ship_date`` falls
        within the lookback window, has a populated
        ``promised_delivery_date``, and has both ``ordered_quantity``
        and ``shipped_quantity``. Each becomes one
        :class:`OtifSample` whose ``on_time`` derives from
        ``last_ship_date <= promised_delivery_date``.

        ``customer_id`` matches ``market_demand_site_id`` (the customer
        site) — that's the canonical join point until the §3.57
        Phase B customer-master mapper lands a richer customer_id
        column on outbound_order_line.

        Optional ``product_id`` narrows by SKU when set.
        """
        from azirella_data_model.master.entities import OutboundOrderLine

        cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).date()
        try:
            customer_site_id = int(customer_id)
        except (TypeError, ValueError):
            # ``customer_id`` not coercible to site id — no canonical
            # mapping yet. Fall through to empty samples.
            log.debug(
                "TmsSampleSource.otif_samples: customer_id %r not "
                "coercible to int site_id; returning []", customer_id,
            )
            return []

        q = (
            db.query(
                OutboundOrderLine.ordered_quantity,
                OutboundOrderLine.shipped_quantity,
                OutboundOrderLine.promised_delivery_date,
                OutboundOrderLine.last_ship_date,
                OutboundOrderLine.first_ship_date,
            )
            .filter(
                OutboundOrderLine.config_id == config_id,
                OutboundOrderLine.market_demand_site_id == customer_site_id,
                OutboundOrderLine.promised_delivery_date.isnot(None),
                OutboundOrderLine.last_ship_date.isnot(None),
                OutboundOrderLine.last_ship_date >= cutoff,
            )
        )
        if product_id is not None:
            q = q.filter(OutboundOrderLine.product_id == product_id)
        rows = q.all()

        samples: list[OtifSample] = []
        for r in rows:
            if not r.ordered_quantity or r.ordered_quantity <= 0:
                continue
            promised_at = self._date_to_ts(r.promised_delivery_date)
            actual_at = self._date_to_ts(
                r.last_ship_date or r.first_ship_date
            )
            if promised_at is None or actual_at is None:
                continue
            samples.append(OtifSample(
                ordered_qty=float(r.ordered_quantity),
                delivered_qty=float(r.shipped_quantity or 0),
                promised_at_ts=promised_at,
                actual_at_ts=actual_at,
            ))
        log.debug(
            "TmsSampleSource.otif_samples: tenant=%s config=%s "
            "customer=%s product=%s lookback=%dd → %d samples",
            tenant_id, config_id, customer_id, product_id,
            lookback_days, len(samples),
        )
        return samples

    @staticmethod
    def _date_to_ts(d) -> Optional[float]:
        """Convert ``date`` / ``datetime`` to POSIX float for
        ``OtifSample.promised_at_ts`` / ``actual_at_ts``."""
        if d is None:
            return None
        if hasattr(d, "timestamp"):
            return float(d.timestamp())
        # ``date`` objects don't have ``timestamp``; promote to
        # midnight datetime.
        return float(datetime(d.year, d.month, d.day).timestamp())


# Compile-time Protocol check.
_: SampleSource = TmsSampleSource()


__all__ = ["TmsSampleSource"]
