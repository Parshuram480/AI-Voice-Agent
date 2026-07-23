-- =============================================================================
-- Voice-Agent CRM Domain Initialization
-- =============================================================================

-- Leads (Identity Table)
CREATE TABLE IF NOT EXISTS leads (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,
    company         VARCHAR(150),
    phone           VARCHAR(20),
    status          VARCHAR(50) DEFAULT 'New'
);

-- Interactions table
CREATE TABLE IF NOT EXISTS interactions (
    id               SERIAL PRIMARY KEY,
    lead_id          INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    date             TIMESTAMPTZ DEFAULT NOW(),
    interaction_type VARCHAR(50) NOT NULL,
    notes            TEXT
);

-- Deals table
CREATE TABLE IF NOT EXISTS deals (
    id                   SERIAL PRIMARY KEY,
    lead_id              INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    amount               DECIMAL(12, 2) NOT NULL,
    stage                VARCHAR(50) NOT NULL,
    expected_close_date  DATE
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO leads (id, full_name, date_of_birth, company, phone, status) VALUES
    (1, 'John Smith', '1985-04-12', 'TechCorp', '+15551234567', 'Qualified'),
    (2, 'Bob Johnson', '1990-11-23', 'Global Solutions', '+15559876543', 'Contacted'),
    (3, 'Charlie Brown', '1978-08-30', 'Innovate LLC', '+15554567890', 'New')
ON CONFLICT (id) DO NOTHING;

SELECT setval('leads_id_seq', (SELECT MAX(id) FROM leads));

INSERT INTO interactions (id, lead_id, date, interaction_type, notes) VALUES
    (1, 1, NOW() - INTERVAL '3 days', 'Email', 'Sent initial pitch deck.'),
    (2, 1, NOW() - INTERVAL '1 day', 'Call', 'Discussed pricing models.'),
    (3, 2, NOW() - INTERVAL '5 hours', 'Email', 'Follow up after trade show.')
ON CONFLICT (id) DO NOTHING;

SELECT setval('interactions_id_seq', (SELECT MAX(id) FROM interactions));

INSERT INTO deals (id, lead_id, amount, stage, expected_close_date) VALUES
    (1, 1, 50000.00, 'Negotiation', CURRENT_DATE + INTERVAL '10 days'),
    (2, 2, 15000.00, 'Proposal Sent', CURRENT_DATE + INTERVAL '30 days')
ON CONFLICT (id) DO NOTHING;

SELECT setval('deals_id_seq', (SELECT MAX(id) FROM deals));
