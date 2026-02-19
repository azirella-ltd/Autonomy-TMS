-- Add round_time_limit column to games table
ALTER TABLE games 
ADD COLUMN IF NOT EXISTS round_time_limit INT NOT NULL DEFAULT 60;

-- Add current_round_ends_at column to games table
ALTER TABLE games 
ADD COLUMN IF NOT EXISTS current_round_ends_at DATETIME NULL;

-- Add is_processed column to game_rounds table
ALTER TABLE game_rounds 
ADD COLUMN IF NOT EXISTS is_processed BOOLEAN NOT NULL DEFAULT FALSE;

-- Add is_completed and completed_at columns if they don't exist
ALTER TABLE game_rounds 
ADD COLUMN IF NOT EXISTS is_completed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE game_rounds 
ADD COLUMN IF NOT EXISTS completed_at DATETIME NULL;
