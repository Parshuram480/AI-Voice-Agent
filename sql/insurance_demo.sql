-- =============================================================================
-- Voice-Agent Insurance Domain Initialization
-- =============================================================================

-- Policyholders (Identity Table)
CREATE TABLE IF NOT EXISTS policyholders (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,
    phone           VARCHAR(20),
    ssn_last4       VARCHAR(4)
);

-- Policies table
CREATE TABLE IF NOT EXISTS policies (
    id               SERIAL PRIMARY KEY,
    policyholder_id  INTEGER NOT NULL REFERENCES policyholders(id) ON DELETE CASCADE,
    policy_type      VARCHAR(100) NOT NULL,
    premium          DECIMAL(10, 2) NOT NULL,
    coverage_amount  DECIMAL(12, 2) NOT NULL,
    status           VARCHAR(50) DEFAULT 'Active'
);

-- Claims table
CREATE TABLE IF NOT EXISTS claims (
    id               SERIAL PRIMARY KEY,
    policy_id        INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    claim_amount     DECIMAL(12, 2) NOT NULL,
    date_filed       DATE DEFAULT CURRENT_DATE,
    status           VARCHAR(50) DEFAULT 'Pending',
    description      TEXT
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO policyholders (id, full_name, date_of_birth, phone, ssn_last4) VALUES
    (1, 'Alice Smith', '1985-04-12', '+15551234567', '4321'),
    (2, 'Bob Johnson', '1990-11-23', '+15559876543', '8765'),
    (3, 'Charlie Brown', '1978-08-30', '+15554567890', '0987')
ON CONFLICT (id) DO NOTHING;

SELECT setval('policyholders_id_seq', (SELECT MAX(id) FROM policyholders));

INSERT INTO policies (id, policyholder_id, policy_type, premium, coverage_amount, status) VALUES
    (1, 1, 'Auto Insurance', 120.00, 50000.00, 'Active'),
    (2, 1, 'Home Insurance', 250.00, 350000.00, 'Active'),
    (3, 2, 'Health Insurance', 300.00, 1000000.00, 'Active'),
    (4, 3, 'Auto Insurance', 150.00, 30000.00, 'Expired')
ON CONFLICT (id) DO NOTHING;

SELECT setval('policies_id_seq', (SELECT MAX(id) FROM policies));

INSERT INTO claims (id, policy_id, claim_amount, date_filed, status, description) VALUES
    (1, 1, 1200.50, CURRENT_DATE - INTERVAL '5 days', 'Approved', 'Fender bender on highway'),
    (2, 2, 4500.00, CURRENT_DATE - INTERVAL '15 days', 'Pending', 'Roof leak damage'),
    (3, 3, 350.00, CURRENT_DATE - INTERVAL '2 days', 'Approved', 'Routine medical checkup')
ON CONFLICT (id) DO NOTHING;

SELECT setval('claims_id_seq', (SELECT MAX(id) FROM claims));
