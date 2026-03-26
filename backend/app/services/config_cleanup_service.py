"""Config Cleanup Service — FK-aware deletion of all data for a supply chain config.

Uses information_schema to dynamically discover all tables referencing
product and site, then deletes in correct FK order. No hardcoded table lists.

Usage:
    from app.services.config_cleanup_service import cleanup_config
    cleanup_config(config_id, db_url)
"""

import logging
from typing import List, Tuple

import psycopg2

logger = logging.getLogger(__name__)


def _get_fk_dependents(cursor, parent_table: str) -> List[Tuple[str, str]]:
    """Get all (table, column) pairs that have FK references to parent_table."""
    cursor.execute("""
        SELECT DISTINCT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE ccu.table_name = %s
            AND tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
            AND tc.table_name != %s
    """, (parent_table, parent_table))
    return [(row[0], row[1]) for row in cursor.fetchall()]


def cleanup_config(config_id: int, db_url: str, dry_run: bool = False) -> dict:
    """Delete all data for a config, handling FK dependencies dynamically.

    Uses multi-pass deletion: keeps iterating until all FK references
    to product and site are cleared, then deletes core tables.

    Args:
        config_id: SupplyChainConfig ID to clean
        db_url: PostgreSQL connection URL
        dry_run: If True, report what would be deleted without deleting

    Returns:
        dict of table_name → rows_deleted
    """
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cursor = conn.cursor()
    deleted = {}

    try:
        # Phase 1: Delete all tables that have config_id column
        cursor.execute("""
            SELECT table_name FROM information_schema.columns
            WHERE column_name = 'config_id' AND table_schema = 'public'
            AND table_name NOT IN ('supply_chain_configs')
            ORDER BY table_name
        """)
        config_tables = [row[0] for row in cursor.fetchall()]

        # Multi-pass: delete config_id tables (some may have FK deps on each other)
        for pass_num in range(3):
            for table in config_tables:
                if table in ("site", "product"):
                    continue
                try:
                    cursor.execute(f"SAVEPOINT sp_{table}_{pass_num}")
                    if dry_run:
                        cursor.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE config_id = %s",
                            (config_id,),
                        )
                        count = cursor.fetchone()[0]
                    else:
                        cursor.execute(
                            f"DELETE FROM {table} WHERE config_id = %s",
                            (config_id,),
                        )
                        count = cursor.rowcount
                    cursor.execute(f"RELEASE SAVEPOINT sp_{table}_{pass_num}")
                    if count > 0:
                        deleted[table] = deleted.get(table, 0) + count
                        logger.info(f"  {table}: {count} rows")
                except Exception:
                    cursor.execute(f"ROLLBACK TO SAVEPOINT sp_{table}_{pass_num}")
                    cursor.execute(f"RELEASE SAVEPOINT sp_{table}_{pass_num}")

        # Phase 2: Delete product FK dependents (tables without config_id)
        product_deps = _get_fk_dependents(cursor, "product")
        for table, column in product_deps:
            if table in deleted and table in config_tables:
                continue  # Already handled via config_id
            try:
                cursor.execute(f"SAVEPOINT sp_prod_{table}")
                if dry_run:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {column} IN "
                        f"(SELECT id FROM product WHERE config_id = %s)",
                        (config_id,),
                    )
                    count = cursor.fetchone()[0]
                else:
                    cursor.execute(
                        f"DELETE FROM {table} WHERE {column} IN "
                        f"(SELECT id FROM product WHERE config_id = %s)",
                        (config_id,),
                    )
                    count = cursor.rowcount
                cursor.execute(f"RELEASE SAVEPOINT sp_prod_{table}")
                if count > 0:
                    deleted[f"{table}.{column}"] = count
                    logger.info(f"  {table}.{column}: {count} rows (product FK)")
            except Exception:
                cursor.execute(f"ROLLBACK TO SAVEPOINT sp_prod_{table}")
                cursor.execute(f"RELEASE SAVEPOINT sp_prod_{table}")

        # Phase 3: Delete site FK dependents
        site_deps = _get_fk_dependents(cursor, "site")
        for table, column in site_deps:
            if table in deleted and table in config_tables:
                continue
            try:
                cursor.execute(f"SAVEPOINT sp_site_{table}")
                if dry_run:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {column} IN "
                        f"(SELECT id FROM site WHERE config_id = %s)",
                        (config_id,),
                    )
                    count = cursor.fetchone()[0]
                else:
                    cursor.execute(
                        f"DELETE FROM {table} WHERE {column} IN "
                        f"(SELECT id FROM site WHERE config_id = %s)",
                        (config_id,),
                    )
                    count = cursor.rowcount
                cursor.execute(f"RELEASE SAVEPOINT sp_site_{table}")
                if count > 0:
                    deleted[f"{table}.{column}"] = count
                    logger.info(f"  {table}.{column}: {count} rows (site FK)")
            except Exception:
                cursor.execute(f"ROLLBACK TO SAVEPOINT sp_site_{table}")
                cursor.execute(f"RELEASE SAVEPOINT sp_site_{table}")

        # Phase 4: Delete core tables
        for core_table in ("product", "transportation_lane", "site"):
            try:
                if dry_run:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {core_table} WHERE config_id = %s",
                        (config_id,),
                    )
                    count = cursor.fetchone()[0]
                else:
                    cursor.execute(
                        f"DELETE FROM {core_table} WHERE config_id = %s",
                        (config_id,),
                    )
                    count = cursor.rowcount
                if count > 0:
                    deleted[core_table] = count
                    logger.info(f"  {core_table}: {count} rows (core)")
            except Exception as e:
                logger.error(f"  FAILED to delete {core_table}: {e}")
                conn.rollback()
                raise

        if not dry_run:
            conn.commit()
        logger.info(f"Config {config_id} cleanup complete: {sum(deleted.values())} total rows")

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return deleted
