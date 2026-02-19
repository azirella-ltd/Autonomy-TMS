-- Sprint 5 Day 5: Performance Optimization - Database Indexes
-- Date: 2026-01-15
-- Purpose: Add strategic indexes to improve query performance

-- Check if indexes already exist before creating
SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0;

-- ============================================================================
-- Player Rounds Indexes (Most Queried Table)
-- ============================================================================

-- Composite index for game and round queries
CREATE INDEX IF NOT EXISTS idx_player_rounds_game_round_player
ON player_rounds(game_id, round_number, player_id);

-- Index for player-specific queries
CREATE INDEX IF NOT EXISTS idx_player_rounds_player_game
ON player_rounds(player_id, game_id, round_number DESC);

-- Index for date-based queries
CREATE INDEX IF NOT EXISTS idx_player_rounds_created
ON player_rounds(created_at DESC);

-- ============================================================================
-- Negotiations Indexes
-- ============================================================================

-- Status and expiration for active negotiations
CREATE INDEX IF NOT EXISTS idx_negotiations_status_expires
ON negotiations(game_id, status, expires_at);

-- Player-specific negotiations
CREATE INDEX IF NOT EXISTS idx_negotiations_proposer
ON negotiations(proposer_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_negotiations_recipient
ON negotiations(recipient_id, status, created_at DESC);

-- Combined players index
CREATE INDEX IF NOT EXISTS idx_negotiations_players
ON negotiations(game_id, proposer_id, recipient_id);

-- ============================================================================
-- Visibility Sharing Indexes
-- ============================================================================

-- Game and round visibility
CREATE INDEX IF NOT EXISTS idx_visibility_game_round
ON visibility_snapshots(game_id, round_number DESC);

-- Player visibility history
CREATE INDEX IF NOT EXISTS idx_visibility_player_round
ON visibility_snapshots(game_id, player_id, round_number DESC);

-- Visibility agreements
CREATE INDEX IF NOT EXISTS idx_visibility_agreements_game
ON visibility_agreements(game_id, is_active, created_at DESC);

-- ============================================================================
-- AI Pattern Analysis Indexes
-- ============================================================================

-- Player patterns lookup
CREATE INDEX IF NOT EXISTS idx_patterns_player_game
ON player_patterns(player_id, game_id, created_at DESC);

-- Pattern type filtering
CREATE INDEX IF NOT EXISTS idx_patterns_type
ON player_patterns(pattern_type, confidence DESC);

-- ============================================================================
-- Achievement & Gamification Indexes
-- ============================================================================

-- Player achievements with unlock date
CREATE INDEX IF NOT EXISTS idx_player_achievements_player_unlocked
ON player_achievements(player_id, unlocked_at DESC);

-- Achievement progress tracking
CREATE INDEX IF NOT EXISTS idx_player_achievements_progress
ON player_achievements(player_id, achievement_id, progress);

-- Leaderboard rankings
CREATE INDEX IF NOT EXISTS idx_leaderboard_entries_rank
ON leaderboard_entries(leaderboard_id, rank ASC);

CREATE INDEX IF NOT EXISTS idx_leaderboard_entries_score
ON leaderboard_entries(leaderboard_id, score DESC);

-- Player stats for leaderboards
CREATE INDEX IF NOT EXISTS idx_player_stats_points
ON player_stats(total_points DESC, player_level DESC);

CREATE INDEX IF NOT EXISTS idx_player_stats_level
ON player_stats(player_level DESC, total_points DESC);

-- Win rate calculations
CREATE INDEX IF NOT EXISTS idx_player_stats_winrate
ON player_stats(total_games_won DESC, total_games_played DESC);

-- ============================================================================
-- Chat & Messaging Indexes
-- ============================================================================

-- Game chat messages
CREATE INDEX IF NOT EXISTS idx_chat_messages_game_time
ON chat_messages(game_id, created_at DESC);

-- User messages
CREATE INDEX IF NOT EXISTS idx_chat_messages_user
ON chat_messages(user_id, created_at DESC);

-- Agent suggestions
CREATE INDEX IF NOT EXISTS idx_agent_suggestions_player_round
ON agent_suggestions(player_id, game_id, round_number);

-- What-if analyses
CREATE INDEX IF NOT EXISTS idx_whatif_analyses_player
ON what_if_analyses(player_id, created_at DESC);

-- ============================================================================
-- Games & Players Indexes
-- ============================================================================

-- Active games
CREATE INDEX IF NOT EXISTS idx_games_status_created
ON games(status, created_at DESC);

-- Player game participation
CREATE INDEX IF NOT EXISTS idx_players_user_game
ON players(user_id, game_id);

CREATE INDEX IF NOT EXISTS idx_players_game_role
ON players(game_id, role);

-- ============================================================================
-- Notification Indexes
-- ============================================================================

-- Unread notifications
CREATE INDEX IF NOT EXISTS idx_achievement_notifications_unread
ON achievement_notifications(player_id, is_read, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_achievement_notifications_shown
ON achievement_notifications(player_id, is_shown, created_at DESC);

-- ============================================================================
-- Analyze Tables for Query Optimizer
-- ============================================================================

ANALYZE TABLE player_rounds;
ANALYZE TABLE negotiations;
ANALYZE TABLE visibility_snapshots;
ANALYZE TABLE visibility_agreements;
ANALYZE TABLE player_patterns;
ANALYZE TABLE player_achievements;
ANALYZE TABLE leaderboard_entries;
ANALYZE TABLE player_stats;
ANALYZE TABLE chat_messages;
ANALYZE TABLE agent_suggestions;
ANALYZE TABLE what_if_analyses;
ANALYZE TABLE games;
ANALYZE TABLE players;
ANALYZE TABLE achievement_notifications;

-- ============================================================================
-- Show Index Statistics
-- ============================================================================

SELECT
    TABLE_NAME,
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    CARDINALITY
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'player_rounds',
    'negotiations',
    'visibility_snapshots',
    'player_achievements',
    'leaderboard_entries',
    'player_stats'
  )
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- ============================================================================
-- Performance Recommendations
-- ============================================================================

-- Show table sizes
SELECT
    TABLE_NAME,
    ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS Size_MB,
    TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'player_rounds',
    'negotiations',
    'visibility_snapshots',
    'player_achievements',
    'leaderboard_entries'
  )
ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC;

SET SQL_NOTES=@OLD_SQL_NOTES;

-- ============================================================================
-- Migration Complete
-- ============================================================================

SELECT CONCAT(
    'Performance indexes migration complete. ',
    'Created ', COUNT(*), ' indexes.'
) AS Status
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND INDEX_NAME LIKE 'idx_%'
  AND CREATE_TIME >= DATE_SUB(NOW(), INTERVAL 1 MINUTE);
