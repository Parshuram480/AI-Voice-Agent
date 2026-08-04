-- =============================================================================
-- Voice-Agent Logistics Domain Initialization
-- =============================================================================

-- Clients (Identity Table)
CREATE TABLE IF NOT EXISTS clients (
    id                SERIAL PRIMARY KEY,
    full_name         VARCHAR(200) NOT NULL,
    date_of_birth     DATE NOT NULL,
    company_name      VARCHAR(150),
    phone             VARCHAR(20)
);

-- Shipments table
CREATE TABLE IF NOT EXISTS shipments (
    id                SERIAL PRIMARY KEY,
    client_id         INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    tracking_number   VARCHAR(50) UNIQUE NOT NULL,
    origin            VARCHAR(150) NOT NULL,
    destination       VARCHAR(150) NOT NULL,
    status            VARCHAR(50) DEFAULT 'Processing',
    estimated_delivery DATE
);

-- Milestones table
CREATE TABLE IF NOT EXISTS milestones (
    id                SERIAL PRIMARY KEY,
    shipment_id       INTEGER NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    location          VARCHAR(150),
    timestamp         TIMESTAMPTZ DEFAULT NOW(),
    status_update     VARCHAR(100)
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO clients (id, full_name, date_of_birth, company_name, phone) VALUES
    (1, 'Alice Smith', '1985-04-12', 'Acme Corp', '+15551234567'),
    (2, 'Bob Johnson', '1990-11-23', 'Globex', '+15559876543'),
    (3, 'Charlie Brown', '1978-08-30', 'Stark Industries', '+15554567890')
ON CONFLICT (id) DO NOTHING;

SELECT setval('clients_id_seq', (SELECT MAX(id) FROM clients));

INSERT INTO shipments (id, client_id, tracking_number, origin, destination, status, estimated_delivery) VALUES
    (1, 1, 'TRK123456789', 'New York, NY', 'Los Angeles, CA', 'In Transit', CURRENT_DATE + INTERVAL '2 days'),
    (2, 1, 'TRK987654321', 'Chicago, IL', 'Miami, FL', 'Delivered', CURRENT_DATE - INTERVAL '1 day'),
    (3, 2, 'TRK555555555', 'Seattle, WA', 'Austin, TX', 'Processing', CURRENT_DATE + INTERVAL '5 days')
ON CONFLICT (id) DO NOTHING;

SELECT setval('shipments_id_seq', (SELECT MAX(id) FROM shipments));

INSERT INTO milestones (id, shipment_id, location, timestamp, status_update) VALUES
    (1, 1, 'New York Distribution Center', NOW() - INTERVAL '1 day', 'Package received'),
    (2, 1, 'Denver Hub', NOW() - INTERVAL '5 hours', 'Departed facility'),
    (3, 2, 'Miami Local Facility', NOW() - INTERVAL '2 days', 'Out for delivery'),
    (4, 2, 'Miami, FL', NOW() - INTERVAL '1 day', 'Delivered')
ON CONFLICT (id) DO NOTHING;

SELECT setval('milestones_id_seq', (SELECT MAX(id) FROM milestones));
