-- PostgreSQL initialization script for JuryAI
-- Creates schema, tables, and indexes for audit logs and metadata

-- Create schema
CREATE SCHEMA IF NOT EXISTS juryai;
GRANT ALL ON SCHEMA juryai TO postgres;

-- Set search path
SET search_path TO juryai, public;

-- Audit log table
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    conversation_id UUID NOT NULL,
    turn_id UUID NOT NULL,
    user_id UUID,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    intent VARCHAR(64),
    sources_used INTEGER DEFAULT 0,
    verification_verdict VARCHAR(32),
    verification_score REAL,
    latency_ms INTEGER,
    model_provider VARCHAR(64),
    model_name VARCHAR(64),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for audit_log
CREATE INDEX IF NOT EXISTS idx_audit_log_conversation_id ON audit_log (conversation_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_verification ON audit_log (verification_verdict);

-- Conversation metadata table
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    title VARCHAR(512),
    user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Turn/messages table
CREATE TABLE IF NOT EXISTS turns (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    verification JSONB,
    citations JSONB,
    sources JSONB,
    intent VARCHAR(64),
    latency_ms INTEGER,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for turns
CREATE INDEX IF NOT EXISTS idx_turns_conversation_id ON turns (conversation_id, turn_number);

-- Document ingestion tracking
CREATE TABLE IF NOT EXISTS ingestion_manifest (
    id BIGSERIAL PRIMARY KEY,
    s3_key VARCHAR(1024) NOT NULL UNIQUE,
    bucket VARCHAR(256),
    file_size BIGINT,
    content_hash VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'pending', -- pending, ingested, failed, skipped
    error TEXT,
    chunks_count INTEGER DEFAULT 0,
    ingested_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for ingestion_manifest
CREATE INDEX IF NOT EXISTS idx_ingestion_manifest_status ON ingestion_manifest (status);
CREATE INDEX IF NOT EXISTS idx_ingestion_manifest_bucket_key ON ingestion_manifest (bucket, s3_key);

-- Session store for interact mode
CREATE TABLE IF NOT EXISTS session_documents (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    document_id VARCHAR(256) NOT NULL,
    filename VARCHAR(512),
    file_size BIGINT,
    content_hash VARCHAR(64),
    chunks_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE(session_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_session_documents_session_id ON session_documents (session_id);
CREATE INDEX IF NOT EXISTS idx_session_documents_expires_at ON session_documents (expires_at);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_conversations_updated_at ON conversations;
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_ingestion_manifest_updated_at ON ingestion_manifest;
CREATE TRIGGER update_ingestion_manifest_updated_at
    BEFORE UPDATE ON ingestion_manifest
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA juryai TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA juryai TO postgres;

-- Comments
COMMENT ON TABLE audit_log IS 'Immutable audit log for compliance and debugging';
COMMENT ON TABLE conversations IS 'Conversation metadata and titles';
COMMENT ON TABLE turns IS 'Individual question-answer turns with verification data';
COMMENT ON TABLE ingestion_manifest IS 'Tracks S3 document ingestion status';
COMMENT ON TABLE session_documents IS 'Per-session document store for interact mode';