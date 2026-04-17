-- 02 — Civio database schema (PostgreSQL 16)
-- This is the authoritative DDL. Alembic migrations must produce this schema.
-- Claude Code MUST regenerate migrations from models and verify against this file.

-- ===========================================================================
-- Extensions
-- ===========================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";           -- fuzzy search on names

-- ===========================================================================
-- Enums
-- ===========================================================================
CREATE TYPE community_status AS ENUM ('pending', 'ready', 'active', 'suspended');
CREATE TYPE ownership_status AS ENUM ('owned', 'sold', 'pending_transfer', 'rented');
CREATE TYPE occupancy_status AS ENUM ('vacant', 'occupied', 'rented');
CREATE TYPE user_role AS ENUM ('owner', 'tenant', 'family', 'admin', 'staff');
CREATE TYPE auth_status AS ENUM ('pending', 'verified', 'revoked');
CREATE TYPE relation_type AS ENUM ('resident', 'family', 'tenant');
CREATE TYPE friend_status AS ENUM ('pending', 'active', 'blocked', 'removed');
CREATE TYPE token_scope AS ENUM ('community', 'user');
CREATE TYPE call_status AS ENUM ('init', 'ringing', 'answered', 'ended', 'rejected', 'failed');
CREATE TYPE billing_scope AS ENUM ('user', 'community', 'free');
CREATE TYPE sync_ack_status AS ENUM ('pending', 'acked', 'failed');
CREATE TYPE announcement_priority AS ENUM ('low', 'normal', 'high', 'urgent');

-- ===========================================================================
-- 1. Community (top-level tenant)
-- ===========================================================================
CREATE TABLE communities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(128) NOT NULL,
    sip_domain      VARCHAR(128) NOT NULL UNIQUE,
    status          community_status NOT NULL DEFAULT 'pending',
    current_version BIGINT NOT NULL DEFAULT 0,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_communities_status ON communities(status);
CREATE INDEX idx_communities_name_trgm ON communities USING gin (name gin_trgm_ops);

-- ===========================================================================
-- 2. Unit (dwelling / apartment)
-- ===========================================================================
CREATE TABLE units (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    community_id      UUID NOT NULL REFERENCES communities(id) ON DELETE RESTRICT,
    unit_code         VARCHAR(64) NOT NULL,           -- e.g. "A1-1203"
    building_no       VARCHAR(32),
    floor_no          INT,
    room_no           VARCHAR(32),
    ownership_status  ownership_status NOT NULL DEFAULT 'owned',
    occupancy_status  occupancy_status NOT NULL DEFAULT 'vacant',
    sync_version      BIGINT NOT NULL DEFAULT 0,
    metadata          JSONB NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (community_id, unit_code)
);
CREATE INDEX idx_units_community ON units(community_id);
CREATE INDEX idx_units_ownership ON units(ownership_status);

-- ===========================================================================
-- 3. User
-- ===========================================================================
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    community_id        UUID NOT NULL REFERENCES communities(id) ON DELETE RESTRICT,
    name                VARCHAR(64) NOT NULL,
    mobile              VARCHAR(32) NOT NULL,
    email               VARCHAR(128),
    role                user_role NOT NULL,
    auth_status         auth_status NOT NULL DEFAULT 'pending',
    call_policy_group   VARCHAR(32),                  -- default policy bundle
    friendship_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (community_id, mobile)
);
CREATE INDEX idx_users_mobile ON users(mobile);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_community ON users(community_id);

-- ===========================================================================
-- 4. User-Unit relation (many-to-many across time)
-- ===========================================================================
CREATE TABLE user_unit_relations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unit_id         UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    relation_type   relation_type NOT NULL,
    effective_from  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to    TIMESTAMPTZ,                     -- NULL = currently active
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_effective_range CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX idx_uur_user ON user_unit_relations(user_id) WHERE effective_to IS NULL;
CREATE INDEX idx_uur_unit ON user_unit_relations(unit_id) WHERE effective_to IS NULL;

-- ===========================================================================
-- 5. SIP endpoint (1:1 with user)
-- ===========================================================================
CREATE TABLE sip_endpoints (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    community_id    UUID NOT NULL REFERENCES communities(id) ON DELETE RESTRICT,
    username        VARCHAR(64) NOT NULL,
    password_hash   VARCHAR(128) NOT NULL,           -- bcrypt hashed
    transport       VARCHAR(16) NOT NULL DEFAULT 'tls',
    context         VARCHAR(64) NOT NULL,            -- dialplan context
    codec_order     TEXT[] NOT NULL DEFAULT ARRAY['opus', 'PCMU', 'PCMA'],
    webrtc_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (community_id, username)
);
CREATE INDEX idx_sip_endpoints_user ON sip_endpoints(user_id);
CREATE INDEX idx_sip_endpoints_community ON sip_endpoints(community_id);

-- ===========================================================================
-- 6. Friend mapping (directed pairs with mutual confirmation)
-- ===========================================================================
CREATE TABLE friend_mappings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_a_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_b_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          friend_status NOT NULL DEFAULT 'pending',
    initiated_by    UUID NOT NULL REFERENCES users(id),
    effective_from  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_distinct_users CHECK (user_a_id <> user_b_id),
    CONSTRAINT ck_sorted_users CHECK (user_a_id < user_b_id)
);
CREATE INDEX idx_friend_active ON friend_mappings(user_a_id, user_b_id) WHERE status = 'active';

-- ===========================================================================
-- 7. Token ledger (APPEND-ONLY)
-- ===========================================================================
CREATE TABLE token_ledger (
    id              BIGSERIAL PRIMARY KEY,
    scope           token_scope NOT NULL,
    community_id    UUID NOT NULL REFERENCES communities(id) ON DELETE RESTRICT,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    delta           NUMERIC(18, 4) NOT NULL,           -- + = credit, - = debit
    balance_after   NUMERIC(18, 4) NOT NULL,
    reason          VARCHAR(64) NOT NULL,              -- 'call', 'topup', 'refund', 'adjustment'
    external_ref    VARCHAR(128),                      -- payment id, call id, etc.
    idempotency_key VARCHAR(128) UNIQUE,               -- prevents double-entry
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_scope_owner CHECK (
        (scope = 'community' AND user_id IS NULL) OR
        (scope = 'user' AND user_id IS NOT NULL)
    )
);
CREATE INDEX idx_ledger_community ON token_ledger(community_id, created_at DESC);
CREATE INDEX idx_ledger_user ON token_ledger(user_id, created_at DESC) WHERE user_id IS NOT NULL;

-- NO UPDATE OR DELETE ALLOWED — enforced via trigger
CREATE OR REPLACE FUNCTION forbid_ledger_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'token_ledger is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_forbid_ledger_update BEFORE UPDATE ON token_ledger
    FOR EACH ROW EXECUTE FUNCTION forbid_ledger_mutation();
CREATE TRIGGER trg_forbid_ledger_delete BEFORE DELETE ON token_ledger
    FOR EACH ROW EXECUTE FUNCTION forbid_ledger_mutation();

-- Materialized view for current balances
CREATE MATERIALIZED VIEW token_balances AS
SELECT
    scope,
    community_id,
    user_id,
    COALESCE(SUM(delta), 0) AS balance,
    MAX(created_at) AS last_change_at
FROM token_ledger
GROUP BY scope, community_id, user_id;

CREATE UNIQUE INDEX idx_balances_key ON token_balances(scope, community_id, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::UUID));

-- ===========================================================================
-- 8. Call logs (CDR)
-- ===========================================================================
CREATE TABLE call_logs (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sip_call_id           VARCHAR(128) NOT NULL,
    community_id          UUID NOT NULL REFERENCES communities(id) ON DELETE RESTRICT,
    caller_user_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    callee_user_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    caller_sip_uri        VARCHAR(256) NOT NULL,
    callee_sip_uri        VARCHAR(256) NOT NULL,
    callee_type           VARCHAR(16),                 -- family/friend/admin
    call_status           call_status NOT NULL,
    start_time            TIMESTAMPTZ NOT NULL,
    answer_time           TIMESTAMPTZ,
    end_time              TIMESTAMPTZ,
    duration_sec          INT NOT NULL DEFAULT 0,
    hangup_cause          VARCHAR(64),
    billing_scope         billing_scope,
    token_cost            NUMERIC(18, 4) NOT NULL DEFAULT 0,
    reject_reason         VARCHAR(64),
    metadata              JSONB NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (community_id, sip_call_id)
);
CREATE INDEX idx_call_logs_community_start ON call_logs(community_id, start_time DESC);
CREATE INDEX idx_call_logs_caller ON call_logs(caller_user_id, start_time DESC);
CREATE INDEX idx_call_logs_callee ON call_logs(callee_user_id, start_time DESC);

-- ===========================================================================
-- 9. Billing records
-- ===========================================================================
CREATE TABLE billing_records (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id          UUID NOT NULL UNIQUE REFERENCES call_logs(id) ON DELETE RESTRICT,
    community_id     UUID NOT NULL REFERENCES communities(id),
    token_cost       NUMERIC(18, 4) NOT NULL,
    billing_scope    billing_scope NOT NULL,
    ledger_entry_id  BIGINT REFERENCES token_ledger(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_billing_community ON billing_records(community_id, created_at DESC);

-- ===========================================================================
-- 10. Sync events (changes destined for edge)
-- ===========================================================================
CREATE TABLE sync_events (
    id              BIGSERIAL PRIMARY KEY,
    community_id    UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    event_type      VARCHAR(64) NOT NULL,             -- 'user.created', 'sip_endpoint.revoked', etc.
    entity_type     VARCHAR(32) NOT NULL,             -- target table
    entity_id       UUID NOT NULL,                    -- target row
    version         BIGINT NOT NULL,                  -- monotonic per community
    payload         JSONB NOT NULL,
    ack_status      sync_ack_status NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acked_at        TIMESTAMPTZ,
    UNIQUE (community_id, version)
);
CREATE INDEX idx_sync_events_pending ON sync_events(community_id, version) WHERE ack_status = 'pending';

-- ===========================================================================
-- 11. Sync state (per community)
-- ===========================================================================
CREATE TABLE sync_state (
    community_id            UUID PRIMARY KEY REFERENCES communities(id) ON DELETE CASCADE,
    last_full_sync_at       TIMESTAMPTZ,
    last_full_sync_version  BIGINT NOT NULL DEFAULT 0,
    last_delta_version      BIGINT NOT NULL DEFAULT 0,
    merkle_root             VARCHAR(128),
    health_status           VARCHAR(16) NOT NULL DEFAULT 'healthy',  -- healthy/stale/resyncing
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===========================================================================
-- 12. Announcements
-- ===========================================================================
CREATE TABLE announcements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    community_id    UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    author_id       UUID NOT NULL REFERENCES users(id),
    title           VARCHAR(256) NOT NULL,
    body            TEXT NOT NULL,
    priority        announcement_priority NOT NULL DEFAULT 'normal',
    published_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_announcements_community ON announcements(community_id, published_at DESC);

-- ===========================================================================
-- 13. Tasks (交辦)
-- ===========================================================================
CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    community_id    UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users(id),
    assigned_to     UUID REFERENCES users(id),
    title           VARCHAR(256) NOT NULL,
    description     TEXT,
    status          VARCHAR(16) NOT NULL DEFAULT 'open',   -- open/in_progress/resolved/closed
    priority        announcement_priority NOT NULL DEFAULT 'normal',
    due_at          TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tasks_community_status ON tasks(community_id, status);

-- ===========================================================================
-- 14. Audit log (append-only)
-- ===========================================================================
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    community_id    UUID REFERENCES communities(id),
    actor_user_id   UUID REFERENCES users(id),
    action          VARCHAR(64) NOT NULL,
    target_type     VARCHAR(32),
    target_id       UUID,
    payload         JSONB NOT NULL DEFAULT '{}',
    ip_address      INET,
    user_agent      VARCHAR(256),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_community_time ON audit_log(community_id, created_at DESC);
CREATE INDEX idx_audit_actor ON audit_log(actor_user_id, created_at DESC);

-- ===========================================================================
-- 15. Consent records (台灣個資法)
-- ===========================================================================
CREATE TABLE consent_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type    VARCHAR(64) NOT NULL,             -- 'call_recording', 'marketing', 'analytics'
    granted         BOOLEAN NOT NULL,
    version         VARCHAR(16) NOT NULL,             -- policy version
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ,
    ip_address      INET
);
CREATE INDEX idx_consent_user_type ON consent_records(user_id, consent_type);

-- ===========================================================================
-- 16. Processed events (idempotency)
-- ===========================================================================
CREATE TABLE processed_events (
    event_id        VARCHAR(64) PRIMARY KEY,
    consumer_name   VARCHAR(64) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===========================================================================
-- 17. Payment orders
-- ===========================================================================
CREATE TABLE payment_orders (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    community_id    UUID NOT NULL REFERENCES communities(id),
    provider        VARCHAR(32) NOT NULL,             -- 'ecpay', 'newebpay', 'apple_iap'
    provider_ref    VARCHAR(128),
    amount          NUMERIC(18, 2) NOT NULL,
    currency        VARCHAR(8) NOT NULL DEFAULT 'TWD',
    token_credit    NUMERIC(18, 4) NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',   -- pending/paid/failed/refunded
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_payment_user ON payment_orders(user_id, created_at DESC);
CREATE INDEX idx_payment_provider_ref ON payment_orders(provider, provider_ref);

-- ===========================================================================
-- Helper: updated_at trigger
-- ===========================================================================
CREATE OR REPLACE FUNCTION tg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at column
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT table_name FROM information_schema.columns
             WHERE column_name = 'updated_at' AND table_schema = 'public'
    LOOP
        EXECUTE format('CREATE TRIGGER trg_updated_at BEFORE UPDATE ON %I
                        FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at()', t);
    END LOOP;
END $$;

-- ===========================================================================
-- Helper: bump community version on any relevant change (for sync)
-- ===========================================================================
CREATE OR REPLACE FUNCTION tg_bump_community_version()
RETURNS TRIGGER AS $$
DECLARE
    cid UUID;
BEGIN
    cid := COALESCE(NEW.community_id, OLD.community_id);
    UPDATE communities SET current_version = current_version + 1 WHERE id = cid;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_version AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION tg_bump_community_version();
CREATE TRIGGER trg_units_version AFTER INSERT OR UPDATE OR DELETE ON units
    FOR EACH ROW EXECUTE FUNCTION tg_bump_community_version();
CREATE TRIGGER trg_sip_endpoints_version AFTER INSERT OR UPDATE OR DELETE ON sip_endpoints
    FOR EACH ROW EXECUTE FUNCTION tg_bump_community_version();
CREATE TRIGGER trg_friends_version AFTER INSERT OR UPDATE OR DELETE ON friend_mappings
    FOR EACH ROW EXECUTE FUNCTION tg_bump_community_version();
