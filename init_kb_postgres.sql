-- pgvector Knowledge Base Database Initialization Script
-- Purpose: Initialize the separate KB database with pgvector extension

-- =============================================================================
-- ENABLE EXTENSIONS
-- =============================================================================

-- Vector similarity search for RAG (Retrieval-Augmented Generation)
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- GRANT PERMISSIONS
-- =============================================================================

GRANT ALL ON SCHEMA public TO kb_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO kb_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO kb_user;

-- =============================================================================
-- SUCCESS MESSAGE
-- =============================================================================
\echo 'KB PostgreSQL initialization complete!'
\echo 'Database: autonomy_kb'
\echo 'Extension: vector (pgvector)'
