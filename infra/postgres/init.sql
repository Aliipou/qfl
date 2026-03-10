-- QFL Platform — PostgreSQL Schema
-- Append-only audit log + FL round persistence

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- FL Rounds
-- ============================================================
CREATE TABLE IF NOT EXISTS fl_rounds (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    dataset       VARCHAR(100) NOT NULL,
    model_arch    VARCHAR(100) NOT NULL,
    config        JSONB NOT NULL DEFAULT '{}',
    global_accuracy     FLOAT,
    privacy_budget_used FLOAT,
    clients_participated INT DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ
);

CREATE INDEX idx_fl_rounds_status ON fl_rounds(status);
CREATE INDEX idx_fl_rounds_created ON fl_rounds(created_at DESC);

-- ============================================================
-- Client Updates (immutable — never update, only insert)
-- ============================================================
CREATE TABLE IF NOT EXISTS client_updates (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    round_id      UUID NOT NULL REFERENCES fl_rounds(id),
    client_id     VARCHAR(100) NOT NULL,
    tenant_id     VARCHAR(100) NOT NULL,
    weights_hash  VARCHAR(64) NOT NULL,
    num_samples   INT NOT NULL,
    local_loss    FLOAT NOT NULL,
    local_accuracy FLOAT NOT NULL,
    dp_noise_applied BOOLEAN DEFAULT FALSE,
    qkd_key_id    VARCHAR(64),
    submitted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_client_updates_round ON client_updates(round_id);
CREATE INDEX idx_client_updates_tenant ON client_updates(tenant_id);

-- ============================================================
-- Audit Log (EU AI Act — append-only, immutable)
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event         VARCHAR(50) NOT NULL,
    round_id      UUID,
    client_id     VARCHAR(100),
    tenant_id     VARCHAR(100),
    risk_level    VARCHAR(20) NOT NULL DEFAULT 'limited',
    details       JSONB NOT NULL DEFAULT '{}',
    model_card_ref VARCHAR(200),
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Make audit_log truly append-only
CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;

CREATE INDEX idx_audit_log_event ON audit_log(event);
CREATE INDEX idx_audit_log_tenant ON audit_log(tenant_id);
CREATE INDEX idx_audit_log_round ON audit_log(round_id);
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);

-- ============================================================
-- DP Budget Ledger (per tenant)
-- ============================================================
CREATE TABLE IF NOT EXISTS dp_budgets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       VARCHAR(100) NOT NULL UNIQUE,
    epsilon_total   FLOAT NOT NULL DEFAULT 10.0,
    epsilon_consumed FLOAT NOT NULL DEFAULT 0.0,
    delta           FLOAT NOT NULL DEFAULT 1e-5,
    rounds          INT NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dp_budgets_tenant ON dp_budgets(tenant_id);

-- ============================================================
-- Model Cards (EU AI Act Article 9)
-- ============================================================
CREATE TABLE IF NOT EXISTS model_cards (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    round_id      UUID NOT NULL REFERENCES fl_rounds(id),
    tenant_id     VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    dataset       VARCHAR(100) NOT NULL,
    global_accuracy FLOAT,
    dp_epsilon    FLOAT,
    risk_level    VARCHAR(20) NOT NULL DEFAULT 'limited',
    training_data_desc TEXT,
    limitations   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
