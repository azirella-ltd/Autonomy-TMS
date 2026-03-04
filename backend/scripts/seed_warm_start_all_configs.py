"""Generate warm start historical data for all SC configs that have Forecast records.

Run inside the container:
    docker compose exec backend python scripts/seed_warm_start_all_configs.py

Or with a specific config:
    docker compose exec backend python scripts/seed_warm_start_all_configs.py --config-id 22
"""

import argparse
import sys
import os

# Allow running from repo root or scripts/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import sync_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.sc_entities import Forecast
from app.services.warm_start_generator import WarmStartGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate warm start data for SC configs")
    parser.add_argument("--config-id", type=int, default=None, help="Target a specific config ID")
    parser.add_argument("--weeks", type=int, default=52, help="Weeks of history to generate (default: 52)")
    args = parser.parse_args()

    db = sync_session_factory()
    try:
        # Find configs to process
        if args.config_id:
            configs = db.query(SupplyChainConfig).filter(SupplyChainConfig.id == args.config_id).all()
            if not configs:
                print(f"ERROR: Config {args.config_id} not found")
                sys.exit(1)
        else:
            # All configs that have at least one Forecast record
            configs_with_forecasts = (
                db.query(SupplyChainConfig)
                .join(Forecast, Forecast.config_id == SupplyChainConfig.id)
                .distinct()
                .all()
            )
            configs = configs_with_forecasts

        if not configs:
            print("No configs with forecast data found. Run seed scripts first.")
            sys.exit(0)

        print(f"Processing {len(configs)} config(s)...")
        generator = WarmStartGenerator(db)

        for cfg in configs:
            print(f"\n  Config {cfg.id} ({cfg.name or 'unnamed'}, tenant={cfg.tenant_id})...")
            try:
                result = generator.generate_for_config(cfg.id, weeks=args.weeks)
                db.commit()
                if result["status"] == "ok":
                    print(f"    OK: {result['records']} actuals generated")
                else:
                    print(f"    SKIPPED: {result.get('reason', 'unknown')}")
            except Exception as exc:
                db.rollback()
                print(f"    ERROR: {exc}")

        print("\nWarm start complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
