-- ============================================================================
-- Sprint 5: Gamification System Database Schema
-- ============================================================================
-- Created: 2026-01-15
-- Description: Achievement system, player stats, leaderboards, badges
-- ============================================================================

USE beer_game;

-- ============================================================================
-- 1. ACHIEVEMENTS TABLE
-- ============================================================================
-- Stores all available achievements in the system
CREATE TABLE IF NOT EXISTS achievements (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    category ENUM('progression', 'performance', 'social', 'mastery', 'special') NOT NULL DEFAULT 'progression',
    criteria JSON NOT NULL COMMENT 'Achievement unlock criteria',
    points INT NOT NULL DEFAULT 10,
    icon VARCHAR(100) DEFAULT 'trophy',
    rarity ENUM('common', 'uncommon', 'rare', 'epic', 'legendary') NOT NULL DEFAULT 'common',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_category (category),
    INDEX idx_rarity (rarity),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 2. PLAYER_STATS TABLE
-- ============================================================================
-- Aggregate statistics per player across all games
CREATE TABLE IF NOT EXISTS player_stats (
    player_id INT PRIMARY KEY,
    total_games_played INT NOT NULL DEFAULT 0,
    total_games_won INT NOT NULL DEFAULT 0,
    total_rounds_played INT NOT NULL DEFAULT 0,
    total_orders_placed INT NOT NULL DEFAULT 0,
    total_cost DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    avg_service_level DECIMAL(5,2) DEFAULT NULL,
    avg_inventory INT DEFAULT NULL,
    best_game_score DECIMAL(15,2) DEFAULT NULL,
    worst_game_score DECIMAL(15,2) DEFAULT NULL,
    total_achievements_unlocked INT NOT NULL DEFAULT 0,
    total_points INT NOT NULL DEFAULT 0,
    player_level INT NOT NULL DEFAULT 1,
    experience_points INT NOT NULL DEFAULT 0,
    consecutive_wins INT NOT NULL DEFAULT 0,
    longest_win_streak INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    INDEX idx_total_points (total_points DESC),
    INDEX idx_player_level (player_level DESC),
    INDEX idx_games_played (total_games_played DESC),
    INDEX idx_games_won (total_games_won DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 3. PLAYER_ACHIEVEMENTS TABLE
-- ============================================================================
-- Tracks which achievements each player has unlocked
CREATE TABLE IF NOT EXISTS player_achievements (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    player_id INT NOT NULL,
    achievement_id INT NOT NULL,
    game_id INT DEFAULT NULL COMMENT 'Game where achievement was unlocked',
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    progress JSON DEFAULT NULL COMMENT 'Progress data for multi-step achievements',
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (achievement_id) REFERENCES achievements(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE SET NULL,
    UNIQUE KEY unique_player_achievement (player_id, achievement_id),
    INDEX idx_player_unlocked (player_id, unlocked_at DESC),
    INDEX idx_achievement_count (achievement_id),
    INDEX idx_game_achievements (game_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 4. LEADERBOARDS TABLE
-- ============================================================================
-- Different leaderboard types (global, weekly, role-based, etc.)
CREATE TABLE IF NOT EXISTS leaderboards (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    leaderboard_type ENUM('global', 'weekly', 'monthly', 'role', 'game_mode') NOT NULL DEFAULT 'global',
    metric ENUM('total_points', 'win_rate', 'avg_cost', 'service_level', 'efficiency') NOT NULL DEFAULT 'total_points',
    filter_criteria JSON DEFAULT NULL COMMENT 'Additional filtering (role, date range, etc.)',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_type_active (leaderboard_type, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 5. LEADERBOARD_ENTRIES TABLE
-- ============================================================================
-- Current rankings for each leaderboard
CREATE TABLE IF NOT EXISTS leaderboard_entries (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    leaderboard_id INT NOT NULL,
    player_id INT NOT NULL,
    rank INT NOT NULL,
    score DECIMAL(15,2) NOT NULL,
    metadata JSON DEFAULT NULL COMMENT 'Additional data (games played, etc.)',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (leaderboard_id) REFERENCES leaderboards(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    UNIQUE KEY unique_leaderboard_player (leaderboard_id, player_id),
    INDEX idx_leaderboard_rank (leaderboard_id, rank),
    INDEX idx_player_leaderboards (player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 6. PLAYER_BADGES TABLE
-- ============================================================================
-- Special badges earned through achievements or events
CREATE TABLE IF NOT EXISTS player_badges (
    id INT PRIMARY KEY AUTO_INCREMENT,
    player_id INT NOT NULL,
    badge_name VARCHAR(255) NOT NULL,
    badge_description TEXT,
    badge_icon VARCHAR(100) DEFAULT 'badge',
    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP DEFAULT NULL COMMENT 'NULL = permanent badge',
    is_displayed BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Whether player displays this badge',
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    INDEX idx_player_badges (player_id, is_displayed),
    INDEX idx_active_badges (player_id, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 7. ACHIEVEMENT_NOTIFICATIONS TABLE
-- ============================================================================
-- Queue of achievement notifications to show players
CREATE TABLE IF NOT EXISTS achievement_notifications (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    player_id INT NOT NULL,
    achievement_id INT NOT NULL,
    notification_type ENUM('unlock', 'progress', 'milestone') NOT NULL DEFAULT 'unlock',
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_shown BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Whether notification was displayed in UI',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP DEFAULT NULL,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (achievement_id) REFERENCES achievements(id) ON DELETE CASCADE,
    INDEX idx_player_unread (player_id, is_read, created_at DESC),
    INDEX idx_player_unshown (player_id, is_shown, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SEED DEFAULT ACHIEVEMENTS
-- ============================================================================

INSERT INTO achievements (name, description, category, criteria, points, icon, rarity) VALUES
-- Progression Achievements
('First Steps', 'Complete your first game', 'progression',
 '{"games_completed": 1}', 10, 'flag', 'common'),

('Veteran Player', 'Play 10 games', 'progression',
 '{"games_played": 10}', 25, 'star', 'uncommon'),

('Supply Chain Expert', 'Play 50 games', 'progression',
 '{"games_played": 50}', 100, 'trophy', 'rare'),

('Master Planner', 'Play 100 games', 'progression',
 '{"games_played": 100}', 250, 'crown', 'epic'),

-- Performance Achievements
('Cost Cutter', 'Win a game with total cost under 500', 'performance',
 '{"win_with_cost_under": 500}', 50, 'dollar', 'rare'),

('Perfect Service', 'Maintain 100% service level for 10 consecutive rounds', 'performance',
 '{"perfect_service_rounds": 10, "consecutive": true}', 75, 'heart', 'epic'),

('Efficiency Master', 'Win a game with average inventory under 5', 'performance',
 '{"win_with_avg_inventory_under": 5}', 100, 'lightning', 'epic'),

('Zero Waste', 'Complete a game without any backlog', 'performance',
 '{"zero_backlog": true}', 150, 'gem', 'legendary'),

-- Social Achievements
('Team Player', 'Accept 5 AI suggestions', 'social',
 '{"ai_suggestions_accepted": 5}', 20, 'users', 'common'),

('Negotiator', 'Complete 10 successful negotiations', 'social',
 '{"negotiations_completed": 10}', 50, 'handshake', 'uncommon'),

('Collaborator', 'Share supply chain visibility 20 times', 'social',
 '{"visibility_shares": 20}', 30, 'eye', 'uncommon'),

-- Mastery Achievements
('Bullwhip Buster', 'Win a game with bullwhip ratio under 1.5', 'mastery',
 '{"win_with_bullwhip_under": 1.5}', 100, 'target', 'rare'),

('Consistent Winner', 'Win 5 games in a row', 'mastery',
 '{"consecutive_wins": 5}', 150, 'medal', 'epic'),

('Legendary', 'Reach player level 20', 'mastery',
 '{"player_level": 20}', 500, 'dragon', 'legendary'),

-- Special Achievements
('Early Adopter', 'Play during the first month of launch', 'special',
 '{"played_before": "2026-02-15"}', 100, 'rocket', 'rare'),

('Night Owl', 'Complete a game between midnight and 4 AM', 'special',
 '{"completed_between_hours": [0, 4]}', 25, 'moon', 'uncommon'),

('Speed Runner', 'Complete a 20-round game in under 10 minutes', 'special',
 '{"game_duration_under_minutes": 10, "min_rounds": 20}', 75, 'clock', 'rare');

-- ============================================================================
-- CREATE DEFAULT LEADERBOARDS
-- ============================================================================

INSERT INTO leaderboards (name, description, leaderboard_type, metric, is_active) VALUES
('Global Champions', 'Top players by total points earned', 'global', 'total_points', TRUE),
('Best Win Rate', 'Players with the highest win percentage', 'global', 'win_rate', TRUE),
('Cost Efficiency Masters', 'Players with lowest average costs', 'global', 'avg_cost', TRUE),
('Service Excellence', 'Players with best service levels', 'global', 'service_level', TRUE),
('Weekly Champions', 'Top players this week', 'weekly', 'total_points', TRUE),
('Monthly Leaders', 'Top players this month', 'monthly', 'total_points', TRUE);

-- ============================================================================
-- TRIGGERS FOR AUTOMATIC UPDATES
-- ============================================================================

-- Trigger: Update player_stats when achievement is unlocked
DELIMITER $$

CREATE TRIGGER after_achievement_unlock
AFTER INSERT ON player_achievements
FOR EACH ROW
BEGIN
    DECLARE achievement_points INT;

    -- Get points for this achievement
    SELECT points INTO achievement_points
    FROM achievements
    WHERE id = NEW.achievement_id;

    -- Update player stats
    UPDATE player_stats
    SET
        total_achievements_unlocked = total_achievements_unlocked + 1,
        total_points = total_points + achievement_points,
        player_level = FLOOR(SQRT(total_points / 10)) + 1,
        updated_at = NOW()
    WHERE player_id = NEW.player_id;

    -- Create notification
    INSERT INTO achievement_notifications (player_id, achievement_id, notification_type, message)
    SELECT NEW.player_id, NEW.achievement_id, 'unlock',
           CONCAT('Achievement Unlocked: ', name)
    FROM achievements
    WHERE id = NEW.achievement_id;
END$$

DELIMITER ;

-- ============================================================================
-- RECORD MIGRATION
-- ============================================================================

INSERT INTO schema_migrations (version, description, executed_at)
VALUES (
    'sprint5_gamification',
    'Sprint 5 Phase 1: Gamification system with achievements, leaderboards, player stats, and badges',
    NOW()
);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Uncomment to verify installation:

-- SELECT COUNT(*) as achievement_count FROM achievements;
-- SELECT COUNT(*) as leaderboard_count FROM leaderboards;
-- SHOW TRIGGERS LIKE 'after_achievement_unlock';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
