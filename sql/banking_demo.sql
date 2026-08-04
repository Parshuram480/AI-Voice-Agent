-- =============================================================================
-- Voice-Agent Banking Domain Initialization
-- =============================================================================

-- Customers (Identity Table)
CREATE TABLE IF NOT EXISTS customers (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,
    phone           VARCHAR(20),
    email           VARCHAR(100) UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Accounts table
CREATE TABLE IF NOT EXISTS accounts (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    account_type    VARCHAR(50) NOT NULL,
    balance         DECIMAL(12, 2) DEFAULT 0.00,
    status          VARCHAR(50) DEFAULT 'Active',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id               SERIAL PRIMARY KEY,
    account_id       INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    amount           DECIMAL(12, 2) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    date             TIMESTAMPTZ DEFAULT NOW()
);

-- Cards table
CREATE TABLE IF NOT EXISTS cards (
    id                SERIAL PRIMARY KEY,
    customer_id       INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    card_number_last4 VARCHAR(4) NOT NULL,
    status            VARCHAR(50) DEFAULT 'Active',
    expiry            VARCHAR(10) NOT NULL
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO customers (id, full_name, date_of_birth, phone, email) VALUES
    (1, 'Alice Smith', '1985-04-12', '+15551234567', 'alice@example.com'),
    (2, 'Bob Johnson', '1990-11-23', '+15559876543', 'bob@example.com'),
    (3, 'Charlie Brown', '1978-08-30', '+15554567890', 'charlie@example.com')
ON CONFLICT (id) DO NOTHING;

SELECT setval('customers_id_seq', (SELECT MAX(id) FROM customers));

INSERT INTO accounts (id, customer_id, account_type, balance, status) VALUES
    (1, 1, 'Checking', 5430.50, 'Active'),
    (2, 1, 'Savings', 12050.75, 'Active'),
    (3, 2, 'Checking', 890.20, 'Active'),
    (4, 3, 'Credit Card', -450.00, 'Active')
ON CONFLICT (id) DO NOTHING;

SELECT setval('accounts_id_seq', (SELECT MAX(id) FROM accounts));

INSERT INTO transactions (id, account_id, amount, transaction_type, date) VALUES
    (1, 1, 150.00, 'Credit', NOW() - INTERVAL '2 days'),
    (2, 1, 45.50, 'Debit', NOW() - INTERVAL '1 day'),
    (3, 2, 500.00, 'Credit', NOW() - INTERVAL '10 days'),
    (4, 3, 120.00, 'Debit', NOW() - INTERVAL '5 hours')
ON CONFLICT (id) DO NOTHING;

SELECT setval('transactions_id_seq', (SELECT MAX(id) FROM transactions));

INSERT INTO cards (id, customer_id, card_number_last4, status, expiry) VALUES
    (1, 1, '1234', 'Active', '12/28'),
    (2, 2, '5678', 'Active', '05/27'),
    (3, 3, '9012', 'Frozen', '08/25')
ON CONFLICT (id) DO NOTHING;

SELECT setval('cards_id_seq', (SELECT MAX(id) FROM cards));
