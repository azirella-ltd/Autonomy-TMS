#!/usr/bin/env python3
"""
Apply Transfer Order schema migration for simulation support.

This script updates the transfer_order and transfer_order_line_item tables
to support simulation integration with string-based site_ids and scenario-specific fields.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import SessionLocal, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the Transfer Order schema migration."""
    
    migration_sql = """
    -- Step 1: Check if transfer_order table exists
    SELECT COUNT(*) FROM information_schema.tables 
    WHERE table_schema = DATABASE() AND table_name = 'transfer_order';
    """
    
    db = SessionLocal()
    
    try:
        # Check if table exists
        result = db.execute(text(migration_sql))
        table_exists = result.scalar() > 0
        
        if not table_exists:
            logger.info("✓ transfer_order table does not exist yet - will be created with correct schema")
            logger.info("✓ No migration needed - models are up to date")
            return True
        
        logger.info("Found existing transfer_order table - applying migration...")
        
        # Read migration SQL
        migration_file = os.path.join(
            os.path.dirname(__file__),
            '..',
            'app',
            'db',
            'migrations',
            'add_beer_game_to_fields.sql'
        )
        
        with open(migration_file, 'r') as f:
            migration_content = f.read()
        
        # Split into individual statements
        statements = [s.strip() for s in migration_content.split(';') if s.strip() and not s.strip().startswith('--')]
        
        # Execute each statement
        for i, statement in enumerate(statements, 1):
            try:
                logger.info(f"Executing statement {i}/{len(statements)}...")
                db.execute(text(statement))
                db.commit()
                logger.info(f"✓ Statement {i} completed")
            except Exception as e:
                error_msg = str(e)
                # Some statements may fail if columns/indexes already exist - that's OK
                if 'duplicate' in error_msg.lower() or 'exists' in error_msg.lower():
                    logger.warning(f"⚠ Statement {i} skipped (already exists): {error_msg}")
                    db.rollback()
                else:
                    logger.error(f"✗ Statement {i} failed: {error_msg}")
                    db.rollback()
                    raise
        
        logger.info("=" * 80)
        logger.info("✓ Transfer Order migration completed successfully!")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
        
    finally:
        db.close()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
