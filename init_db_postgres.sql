-- PostgreSQL Database Initialization Script
-- Replaces: init_db.sql (MariaDB)
-- Purpose: Initialize database, user, and permissions for Autonomy

-- =============================================================================
-- DATABASE CREATION
-- =============================================================================
-- Note: The POSTGRES_DB environment variable in Docker handles database creation
-- This script runs after the database is created, so we just set permissions

-- Connect to the autonomy database
\c autonomy

-- =============================================================================
-- GRANT PERMISSIONS TO APPLICATION USER
-- =============================================================================
-- Grant all privileges on the database
GRANT ALL PRIVILEGES ON DATABASE autonomy TO autonomy_user;

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO autonomy_user;

-- Grant privileges on all existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO autonomy_user;

-- Grant privileges on all existing sequences
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO autonomy_user;

-- Grant privileges on all existing functions
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO autonomy_user;

-- =============================================================================
-- ALTER DEFAULT PRIVILEGES
-- =============================================================================
-- Ensure future objects created by postgres user are also accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO autonomy_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO autonomy_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO autonomy_user;

-- Allow autonomy_user to create tables and other objects
ALTER ROLE autonomy_user CREATEDB;

-- =============================================================================
-- ENABLE EXTENSIONS
-- =============================================================================
-- Enable useful PostgreSQL extensions

-- UUID generation (if needed for future features)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Full-text search improvements (if needed)
-- CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Query performance statistics (highly recommended)
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Vector similarity search for RAG (Retrieval-Augmented Generation)
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- CREATE CUSTOM TYPES (if needed)
-- =============================================================================
-- PostgreSQL-specific ENUM types can be created here if needed
-- SQLAlchemy will create these automatically from models, so this is optional

-- Example:
-- CREATE TYPE game_status AS ENUM ('pending', 'active', 'completed', 'cancelled');
-- CREATE TYPE player_role AS ENUM ('RETAILER', 'WHOLESALER', 'DISTRIBUTOR', 'FACTORY');

-- =============================================================================
-- OPTIMIZATION SETTINGS
-- =============================================================================
-- Set timezone to UTC for consistency
SET timezone = 'UTC';

-- =============================================================================
-- SUCCESS MESSAGE
-- =============================================================================
\echo 'PostgreSQL initialization complete!'
\echo 'Database: autonomy'
\echo 'User: autonomy_user'
\echo 'Extensions enabled: uuid-ossp, pg_stat_statements, vector (pgvector)'
\echo 'Ready for SQLAlchemy migrations.'
