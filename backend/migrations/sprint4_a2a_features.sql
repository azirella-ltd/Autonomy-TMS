-- Phase 7 Sprint 4 - Advanced A2A Features
-- Database migration for all Sprint 4 tables
-- Date: 2026-01-14

-- =============================================================================
-- 1. CONVERSATION MESSAGES (Multi-Turn Chat)
-- =============================================================================

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    parent_message_id BIGINT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    context JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_message_id) REFERENCES conversation_messages(id) ON DELETE SET NULL,

    INDEX idx_game_player (game_id, player_id),
    INDEX idx_created (created_at),
    INDEX idx_parent (parent_message_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 2. SUGGESTION OUTCOMES (Pattern Analysis)
-- =============================================================================

CREATE TABLE IF NOT EXISTS suggestion_outcomes (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    suggestion_id INT NOT NULL,
    accepted BOOLEAN NOT NULL,
    modified_quantity INT NULL,
    actual_order_placed INT NOT NULL,
    round_result JSON,
    performance_score DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (suggestion_id) REFERENCES agent_suggestions(id) ON DELETE CASCADE,

    INDEX idx_suggestion (suggestion_id),
    INDEX idx_accepted (accepted),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS player_patterns (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    player_id INT NOT NULL,
    game_id INT NOT NULL,
    pattern_type ENUM('conservative', 'aggressive', 'balanced', 'reactive') DEFAULT 'balanced',
    acceptance_rate DECIMAL(5,2) DEFAULT 0.00,
    avg_modification DECIMAL(5,2) DEFAULT 0.00,
    preferred_priorities VARCHAR(255),
    total_suggestions INT DEFAULT 0,
    total_accepted INT DEFAULT 0,
    last_analyzed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,

    UNIQUE KEY uk_player_game (player_id, game_id),
    INDEX idx_pattern_type (pattern_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 3. VISIBILITY SHARING (Shared Dashboard)
-- =============================================================================

CREATE TABLE IF NOT EXISTS visibility_permissions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    share_inventory BOOLEAN DEFAULT FALSE,
    share_backlog BOOLEAN DEFAULT FALSE,
    share_orders BOOLEAN DEFAULT FALSE,
    share_forecast BOOLEAN DEFAULT FALSE,
    share_costs BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,

    UNIQUE KEY uk_game_player (game_id, player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS visibility_snapshots (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    round INT NOT NULL,
    supply_chain_health_score DECIMAL(5,2),
    bottleneck_node VARCHAR(50),
    bullwhip_severity ENUM('low', 'moderate', 'high', 'critical') DEFAULT 'low',
    total_inventory INT DEFAULT 0,
    total_backlog INT DEFAULT 0,
    total_cost DECIMAL(10,2) DEFAULT 0.00,
    metrics JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,

    INDEX idx_game_round (game_id, round),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 4. NEGOTIATIONS (Agent-to-Agent)
-- =============================================================================

CREATE TABLE IF NOT EXISTS negotiations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    initiator_player_id INT NOT NULL,
    target_player_id INT NOT NULL,
    negotiation_type ENUM('expedite_shipment', 'share_info', 'adjust_order', 'coordinate', 'custom') NOT NULL,
    status ENUM('proposed', 'countered', 'accepted', 'rejected', 'expired') DEFAULT 'proposed',
    proposal TEXT NOT NULL,
    counter_proposal TEXT NULL,
    ai_mediation_notes JSON,
    impact_analysis JSON,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,

    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (initiator_player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (target_player_id) REFERENCES players(id) ON DELETE CASCADE,

    INDEX idx_game_status (game_id, status),
    INDEX idx_initiator (initiator_player_id),
    INDEX idx_target (target_player_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS negotiation_messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    negotiation_id BIGINT NOT NULL,
    sender_player_id INT NOT NULL,
    message TEXT NOT NULL,
    message_type ENUM('proposal', 'counter', 'comment', 'system') DEFAULT 'comment',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (negotiation_id) REFERENCES negotiations(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_player_id) REFERENCES players(id) ON DELETE CASCADE,

    INDEX idx_negotiation (negotiation_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 5. GLOBAL OPTIMIZATION HISTORY (Cross-Agent)
-- =============================================================================

CREATE TABLE IF NOT EXISTS optimization_recommendations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    round INT NOT NULL,
    optimization_type ENUM('minimize_cost', 'maximize_service', 'balance', 'reduce_bullwhip') NOT NULL,
    recommendations JSON NOT NULL,
    global_impact JSON,
    acceptance_status JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,

    INDEX idx_game_round (game_id, round),
    INDEX idx_type (optimization_type),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- VIEWS FOR ANALYTICS
-- =============================================================================

-- View: Conversation activity summary per game
CREATE OR REPLACE VIEW v_conversation_activity AS
SELECT
    cm.game_id,
    cm.player_id,
    COUNT(*) as total_messages,
    SUM(CASE WHEN cm.role = 'user' THEN 1 ELSE 0 END) as user_messages,
    SUM(CASE WHEN cm.role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages,
    MIN(cm.created_at) as first_message,
    MAX(cm.created_at) as last_message
FROM conversation_messages cm
GROUP BY cm.game_id, cm.player_id;

-- View: Suggestion acceptance rates per player
CREATE OR REPLACE VIEW v_suggestion_acceptance AS
SELECT
    pp.player_id,
    pp.game_id,
    pp.total_suggestions,
    pp.total_accepted,
    pp.acceptance_rate,
    pp.pattern_type,
    COUNT(so.id) as outcomes_tracked,
    AVG(so.performance_score) as avg_performance
FROM player_patterns pp
LEFT JOIN agent_suggestions ags ON ags.player_id = pp.player_id AND ags.game_id = pp.game_id
LEFT JOIN suggestion_outcomes so ON so.suggestion_id = ags.id
GROUP BY pp.player_id, pp.game_id;

-- View: Active negotiations per game
CREATE OR REPLACE VIEW v_active_negotiations AS
SELECT
    n.game_id,
    COUNT(*) as active_count,
    SUM(CASE WHEN n.status = 'proposed' THEN 1 ELSE 0 END) as proposed,
    SUM(CASE WHEN n.status = 'countered' THEN 1 ELSE 0 END) as countered,
    SUM(CASE WHEN n.status = 'accepted' THEN 1 ELSE 0 END) as accepted,
    SUM(CASE WHEN n.status = 'rejected' THEN 1 ELSE 0 END) as rejected
FROM negotiations n
WHERE n.status IN ('proposed', 'countered')
GROUP BY n.game_id;

-- View: Supply chain visibility sharing per game
CREATE OR REPLACE VIEW v_visibility_sharing AS
SELECT
    vp.game_id,
    COUNT(*) as total_players,
    SUM(CASE WHEN vp.share_inventory THEN 1 ELSE 0 END) as sharing_inventory,
    SUM(CASE WHEN vp.share_backlog THEN 1 ELSE 0 END) as sharing_backlog,
    SUM(CASE WHEN vp.share_orders THEN 1 ELSE 0 END) as sharing_orders,
    SUM(CASE WHEN vp.share_forecast THEN 1 ELSE 0 END) as sharing_forecast,
    ROUND(AVG(CASE WHEN vp.share_inventory THEN 1 ELSE 0 END) * 100, 2) as inventory_share_pct
FROM visibility_permissions vp
GROUP BY vp.game_id;

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

-- Additional composite indexes for common queries
CREATE INDEX idx_conv_game_player_created ON conversation_messages(game_id, player_id, created_at DESC);
CREATE INDEX idx_sugg_outcome_perf ON suggestion_outcomes(performance_score DESC);
CREATE INDEX idx_neg_game_status_expires ON negotiations(game_id, status, expires_at);
CREATE INDEX idx_vis_snap_health ON visibility_snapshots(game_id, supply_chain_health_score DESC);

-- =============================================================================
-- TRIGGERS FOR AUTOMATIC UPDATES
-- =============================================================================

-- Trigger: Update player_patterns when suggestion outcome is recorded
DELIMITER //

CREATE TRIGGER trg_update_player_patterns_after_outcome
AFTER INSERT ON suggestion_outcomes
FOR EACH ROW
BEGIN
    DECLARE v_player_id INT;
    DECLARE v_game_id INT;

    -- Get player and game from suggestion
    SELECT ags.player_id, ags.game_id INTO v_player_id, v_game_id
    FROM agent_suggestions ags
    WHERE ags.id = NEW.suggestion_id;

    -- Insert or update player_patterns
    INSERT INTO player_patterns (player_id, game_id, total_suggestions, total_accepted, acceptance_rate)
    VALUES (v_player_id, v_game_id, 1, IF(NEW.accepted, 1, 0), IF(NEW.accepted, 100.00, 0.00))
    ON DUPLICATE KEY UPDATE
        total_suggestions = total_suggestions + 1,
        total_accepted = total_accepted + IF(NEW.accepted, 1, 0),
        acceptance_rate = (total_accepted * 100.0 / total_suggestions);
END//

-- Trigger: Expire old negotiations automatically
CREATE TRIGGER trg_expire_negotiations_before_update
BEFORE UPDATE ON negotiations
FOR EACH ROW
BEGIN
    IF NEW.status IN ('proposed', 'countered')
       AND NEW.expires_at IS NOT NULL
       AND NEW.expires_at < NOW() THEN
        SET NEW.status = 'expired';
        SET NEW.resolved_at = NOW();
    END IF;
END//

DELIMITER ;

-- =============================================================================
-- INITIAL DATA SEEDING (Optional)
-- =============================================================================

-- You can add default visibility permissions for all existing players
-- INSERT INTO visibility_permissions (game_id, player_id, share_inventory, share_backlog)
-- SELECT g.id, p.id, FALSE, FALSE
-- FROM games g
-- CROSS JOIN players p
-- WHERE NOT EXISTS (
--     SELECT 1 FROM visibility_permissions vp
--     WHERE vp.game_id = g.id AND vp.player_id = p.id
-- );

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================

-- Log migration completion
INSERT INTO schema_migrations (version, description, executed_at)
VALUES (
    'sprint4_a2a_features',
    'Phase 7 Sprint 4: Multi-turn conversations, pattern analysis, visibility sharing, negotiations, global optimization',
    NOW()
)
ON DUPLICATE KEY UPDATE executed_at = NOW();
