-- =============================================================================
-- Voice-Agent Ecommerce Domain Initialization
-- =============================================================================

-- Shoppers (Identity Table)
CREATE TABLE IF NOT EXISTS shoppers (
    id                SERIAL PRIMARY KEY,
    full_name         VARCHAR(200) NOT NULL,
    date_of_birth     DATE NOT NULL,
    email             VARCHAR(100) UNIQUE,
    phone             VARCHAR(20)
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id                SERIAL PRIMARY KEY,
    shopper_id        INTEGER NOT NULL REFERENCES shoppers(id) ON DELETE CASCADE,
    order_number      VARCHAR(50) UNIQUE NOT NULL,
    total_amount      DECIMAL(12, 2) NOT NULL,
    status            VARCHAR(50) DEFAULT 'Processing',
    date              TIMESTAMPTZ DEFAULT NOW()
);

-- Order Items table
CREATE TABLE IF NOT EXISTS order_items (
    id                SERIAL PRIMARY KEY,
    order_id          INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_name      VARCHAR(150) NOT NULL,
    quantity          INTEGER NOT NULL DEFAULT 1,
    price             DECIMAL(10, 2) NOT NULL
);

-- Returns table
CREATE TABLE IF NOT EXISTS returns (
    id                SERIAL PRIMARY KEY,
    order_id          INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    reason            VARCHAR(200),
    status            VARCHAR(50) DEFAULT 'Pending Validation'
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO shoppers (id, full_name, date_of_birth, email, phone) VALUES
    (1, 'Alice Smith', '1985-04-12', 'alice@shop.com', '+15551234567'),
    (2, 'Bob Johnson', '1990-11-23', 'bob@shop.com', '+15559876543'),
    (3, 'Charlie Brown', '1978-08-30', 'charlie@shop.com', '+15554567890')
ON CONFLICT (id) DO NOTHING;

SELECT setval('shoppers_id_seq', (SELECT MAX(id) FROM shoppers));

INSERT INTO orders (id, shopper_id, order_number, total_amount, status, date) VALUES
    (1, 1, 'ORD-1001', 250.50, 'Shipped', NOW() - INTERVAL '2 days'),
    (2, 1, 'ORD-1002', 45.00, 'Delivered', NOW() - INTERVAL '10 days'),
    (3, 2, 'ORD-1003', 1200.00, 'Processing', NOW() - INTERVAL '5 hours')
ON CONFLICT (id) DO NOTHING;

SELECT setval('orders_id_seq', (SELECT MAX(id) FROM orders));

INSERT INTO order_items (id, order_id, product_name, quantity, price) VALUES
    (1, 1, 'Wireless Headphones', 1, 150.00),
    (2, 1, 'Ergonomic Mouse', 1, 100.50),
    (3, 2, 'Phone Case', 2, 22.50),
    (4, 3, 'Laptop Pro', 1, 1200.00)
ON CONFLICT (id) DO NOTHING;

SELECT setval('order_items_id_seq', (SELECT MAX(id) FROM order_items));

INSERT INTO returns (id, order_id, reason, status) VALUES
    (1, 2, 'Wrong size/fit', 'Approved')
ON CONFLICT (id) DO NOTHING;

SELECT setval('returns_id_seq', (SELECT MAX(id) FROM returns));
