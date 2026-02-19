-- Migration: Add Beer Game fields to Transfer Order tables
-- Date: 2026-01-21
-- Purpose: Support Beer Game integration with Transfer Orders

-- Step 1: Modify transfer_order table to support string-based site_ids
ALTER TABLE transfer_order 
  MODIFY COLUMN source_site_id VARCHAR(100) NOT NULL,
  MODIFY COLUMN destination_site_id VARCHAR(100) NOT NULL;

-- Step 2: Add Beer Game specific fields to transfer_order
ALTER TABLE transfer_order
  ADD COLUMN IF NOT EXISTS order_date DATE,
  ADD COLUMN IF NOT EXISTS game_id INT,
  ADD COLUMN IF NOT EXISTS order_round INT,
  ADD COLUMN IF NOT EXISTS arrival_round INT;

-- Step 3: Add foreign key for game_id (if games table exists)
-- Note: This will fail gracefully if the FK already exists
ALTER TABLE transfer_order
  ADD CONSTRAINT fk_transfer_order_game 
  FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE;

-- Step 4: Add indexes for Beer Game queries
CREATE INDEX IF NOT EXISTS idx_to_game_arrival 
  ON transfer_order(game_id, arrival_round, status);

CREATE INDEX IF NOT EXISTS idx_to_game_order 
  ON transfer_order(game_id, order_round);

-- Step 5: Modify transfer_order_line_item to support string-based product_ids
ALTER TABLE transfer_order_line_item
  MODIFY COLUMN product_id VARCHAR(100) NOT NULL;

-- Step 6: Add missing quantity columns if they don't exist
ALTER TABLE transfer_order_line_item
  ADD COLUMN IF NOT EXISTS ordered_quantity DOUBLE DEFAULT 0.0;

-- Migration complete
SELECT 'Transfer Order Beer Game migration completed successfully' AS status;
