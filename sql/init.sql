-- =============================================================================
-- Voice-Agent Database Initialization
-- Run this script against your PostgreSQL database to create the schema
-- and insert sample data for testing.
--
-- Usage:  psql -U postgres -d voice_agent -f sql/init.sql
-- =============================================================================

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,
    phone           VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

-- Index for fast identity verification lookups
CREATE INDEX IF NOT EXISTS idx_customer_lookup
    ON customers (LOWER(full_name), date_of_birth);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id                  SERIAL PRIMARY KEY,
    customer_id         INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    order_number        VARCHAR(50) UNIQUE NOT NULL,
    status              VARCHAR(50) NOT NULL DEFAULT 'Processing',
    estimated_arrival   DATE,
    items_summary       TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

-- Index for fetching latest orders by customer
CREATE INDEX IF NOT EXISTS idx_order_customer
    ON orders (customer_id, created_at DESC);

-- Call Logs table
CREATE TABLE IF NOT EXISTS call_logs (
    session_id              VARCHAR(100) PRIMARY KEY,
    user_id                 INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    pipeline_mode           VARCHAR(50),
    history                 JSONB,
    summary                 TEXT,
    intent                  VARCHAR(100),
    total_input_tokens          INTEGER DEFAULT 0,
    total_output_tokens         INTEGER DEFAULT 0,
    total_input_output_tokens   INTEGER DEFAULT 0,
    summary_input_tokens        INTEGER DEFAULT 0,
    summary_output_tokens       INTEGER DEFAULT 0,
    summary_input_output_tokens INTEGER DEFAULT 0,
    total_tokens                INTEGER DEFAULT 0,
    average_latency         FLOAT,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO customers (full_name, date_of_birth, phone) VALUES
    ('John Smith',    '1990-05-15', '+15551234567'),
    ('Jane Doe',      '1985-11-20', '+15559876543'),
    ('Alice Johnson', '1992-03-08', '+15554567890')
ON CONFLICT DO NOTHING;

INSERT INTO orders (customer_id, order_number, status, estimated_arrival, items_summary) VALUES
    (1, 'ORD-20260501-001', 'Shipped',     '2026-05-25', '2x Wireless Headphones, 1x USB-C Cable'),
    (1, 'ORD-20260510-002', 'Processing',  '2026-05-28', '1x Mechanical Keyboard'),
    (2, 'ORD-20260505-003', 'Delivered',    '2026-05-18', '3x Phone Case, 1x Screen Protector'),
    (3, 'ORD-20260512-004', 'In Transit',   '2026-05-24', '1x Laptop Stand, 2x Monitor Riser')
ON CONFLICT (order_number) DO NOTHING;
