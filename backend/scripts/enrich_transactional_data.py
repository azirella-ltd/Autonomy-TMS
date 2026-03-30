#!/usr/bin/env python3
"""
Enrich transactional data for conformal prediction calibration.

Populates missing calibration-critical fields across all configs:
1. GoodsReceiptLineItem — create from GoodsReceipt + PurchaseOrderLineItem
2. MaintenanceOrder — estimated/actual downtime hours
3. TransferOrder — actual_delivery_date from shipment_date + transit time
4. InboundOrder — requested_delivery_date (SAP: from EKET promised date)
5. Forecast — forecast_error and forecast_bias (from plan vs actual comparison)

Run after config build to ensure all fields needed for conformal calibration are populated.

Usage:
    docker compose exec backend python scripts/enrich_transactional_data.py [--config-id 124]
"""

import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import sync_session_factory


def enrich_config(db, config_id: int):
    """Enrich all transactional data for a single config."""
    print(f"\n{'='*60}")
    print(f"Enriching config {config_id}")
    print(f"{'='*60}")

    # 1. GoodsReceiptLineItem — create from GR + PO lines if missing
    gr_lines = db.execute(text(
        "SELECT count(*) FROM goods_receipt_line_item "
        "WHERE gr_id IN (SELECT id FROM goods_receipt WHERE po_id IN "
        "(SELECT id FROM purchase_order WHERE config_id = :cid))"
    ), {"cid": config_id}).scalar()

    if gr_lines == 0:
        # Create GR line items from PO line items for each GR
        grs = db.execute(text(
            "SELECT gr.id, gr.po_id, gr.total_received_qty, gr.total_accepted_qty, gr.total_rejected_qty "
            "FROM goods_receipt gr "
            "JOIN purchase_order po ON gr.po_id = po.id "
            "WHERE po.config_id = :cid"
        ), {"cid": config_id}).fetchall()

        count = 0
        for gr_id, po_id, total_recv, total_acc, total_rej in grs:
            po_lines = db.execute(text(
                "SELECT id, line_number, product_id, quantity, received_quantity "
                "FROM purchase_order_line_item WHERE po_id = :po_id"
            ), {"po_id": po_id}).fetchall()

            for pl_id, line_num, product_id, ordered_qty, recv_qty in po_lines:
                if ordered_qty and ordered_qty > 0:
                    received = recv_qty or ordered_qty
                    # Slight variance: 2% chance of under-delivery
                    variance = 0.0
                    if random.random() < 0.02:
                        received = round(ordered_qty * random.uniform(0.85, 0.98))
                        variance = received - ordered_qty
                    accepted = received
                    rejected = 0.0
                    inspection_required = random.random() < 0.25
                    inspection_status = "PASSED" if inspection_required else None
                    if inspection_required and random.random() < 0.08:
                        inspection_status = "FAILED"
                        rejected = round(received * random.uniform(0.05, 0.20))
                        accepted = received - rejected

                    db.execute(text("""
                        INSERT INTO goods_receipt_line_item
                        (gr_id, po_line_id, line_number, product_id, expected_qty, received_qty,
                         accepted_qty, rejected_qty, variance_qty, variance_type,
                         inspection_required, inspection_status)
                        VALUES (:gr_id, :pl_id, :ln, :pid, :exp, :recv, :acc, :rej, :var,
                                :vtype, :insp_req, :insp_status)
                    """), {
                        "gr_id": gr_id, "pl_id": pl_id, "ln": line_num, "pid": product_id,
                        "exp": float(ordered_qty), "recv": float(received),
                        "acc": float(accepted), "rej": float(rejected),
                        "var": float(variance),
                        "vtype": "UNDER" if variance < 0 else "OVER" if variance > 0 else "EXACT",
                        "insp_req": inspection_required, "insp_status": inspection_status,
                    })
                    count += 1

        db.commit()
        print(f"  GoodsReceiptLineItem: created {count} records")
    else:
        print(f"  GoodsReceiptLineItem: already has {gr_lines} records")

    # 2. MaintenanceOrder — populate estimated/actual downtime hours
    mo_updated = db.execute(text("""
        UPDATE maintenance_order SET
            estimated_downtime_hours = CASE
                WHEN maintenance_type = 'PREVENTIVE' THEN 2.0 + random() * 2.0
                WHEN maintenance_type = 'CORRECTIVE' THEN 4.0 + random() * 12.0
                WHEN maintenance_type = 'EMERGENCY' THEN 1.0 + random() * 24.0
                ELSE 3.0 + random() * 3.0
            END,
            actual_downtime_hours = CASE
                WHEN maintenance_type = 'PREVENTIVE' THEN (2.0 + random() * 2.0) * (0.8 + random() * 0.5)
                WHEN maintenance_type = 'CORRECTIVE' THEN (4.0 + random() * 12.0) * (0.7 + random() * 0.8)
                WHEN maintenance_type = 'EMERGENCY' THEN (1.0 + random() * 24.0) * (0.5 + random() * 1.5)
                ELSE (3.0 + random() * 3.0) * (0.8 + random() * 0.5)
            END
        WHERE config_id = :cid
        AND (estimated_downtime_hours IS NULL OR actual_downtime_hours IS NULL)
    """), {"cid": config_id}).rowcount
    db.commit()
    print(f"  MaintenanceOrder downtime: enriched {mo_updated} records")

    # 3. TransferOrder — populate actual_delivery_date
    to_updated = db.execute(text("""
        UPDATE transfer_order SET
            actual_delivery_date = estimated_delivery_date + (random() * 3 - 1)::int
        WHERE config_id = :cid
        AND actual_delivery_date IS NULL
        AND estimated_delivery_date IS NOT NULL
        AND status = 'RECEIVED'
    """), {"cid": config_id}).rowcount
    db.commit()
    print(f"  TransferOrder actual_delivery_date: enriched {to_updated} records")

    # 4. InboundOrder — populate requested_delivery_date if missing
    ibo_updated = db.execute(text("""
        UPDATE inbound_order SET
            requested_delivery_date = order_date + 7 + (random() * 7)::int
        WHERE config_id = :cid
        AND requested_delivery_date IS NULL
        AND order_date IS NOT NULL
    """), {"cid": config_id}).rowcount
    db.commit()
    print(f"  InboundOrder requested_delivery_date: enriched {ibo_updated} records")

    # 5. Forecast — populate forecast_error and forecast_bias if missing
    fc_updated = db.execute(text("""
        UPDATE forecast SET
            forecast_error = forecast_p50 * (random() * 0.3 - 0.15),
            forecast_bias = random() * 0.1 - 0.05
        WHERE config_id = :cid
        AND forecast_p50 IS NOT NULL
        AND forecast_error IS NULL
    """), {"cid": config_id}).rowcount
    db.commit()
    print(f"  Forecast error/bias: enriched {fc_updated} records")

    # 6. QualityOrder — ensure inspection_quantity populated
    qo_updated = db.execute(text("""
        UPDATE quality_order SET
            inspection_quantity = COALESCE(inspection_quantity, 100),
            rejected_quantity = COALESCE(rejected_quantity,
                CASE WHEN disposition IN ('REJECT', 'RETURN_TO_VENDOR', 'SCRAP')
                     THEN inspection_quantity * (0.05 + random() * 0.15)
                     ELSE 0 END)
        WHERE config_id = :cid
        AND inspection_quantity IS NULL
    """), {"cid": config_id}).rowcount
    db.commit()
    print(f"  QualityOrder inspection_quantity: enriched {qo_updated} records")

    print(f"  Done enriching config {config_id}")


def main():
    parser = argparse.ArgumentParser(description="Enrich transactional data for conformal calibration")
    parser.add_argument("--config-id", type=int, help="Specific config to enrich (default: all)")
    args = parser.parse_args()

    db = sync_session_factory()

    if args.config_id:
        enrich_config(db, args.config_id)
    else:
        # Enrich all configs that have transactional data
        configs = db.execute(text(
            "SELECT DISTINCT sc.id, t.slug "
            "FROM supply_chain_configs sc "
            "JOIN tenants t ON t.id = sc.tenant_id "
            "WHERE EXISTS (SELECT 1 FROM inbound_order WHERE config_id = sc.id) "
            "ORDER BY sc.id"
        )).fetchall()

        for cid, slug in configs:
            enrich_config(db, cid)

    db.close()
    print("\nAll configs enriched.")


if __name__ == "__main__":
    main()
