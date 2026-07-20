-- =============================================================================
-- Food Delivery Voice Agent Demo Database Initialization
-- =============================================================================

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

CREATE TABLE IF NOT EXISTS customers (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,
    phone_number    VARCHAR(20) NOT NULL,
    delivery_address TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS restaurants (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    cuisine_type    VARCHAR(100),
    rating          DECIMAL(3,1),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    restaurant_id   INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE SET NULL,
    order_status    VARCHAR(50) NOT NULL DEFAULT 'Preparing',
    total_amount    DECIMAL(10,2),
    estimated_delivery_time TIME,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS menu_items (
    id              SERIAL PRIMARY KEY,
    restaurant_id   INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    item_name       VARCHAR(200) NOT NULL,
    price           DECIMAL(10,2) NOT NULL,
    is_available    BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    order_id        INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id    INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    quantity        INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO customers (id, full_name, date_of_birth, phone_number, delivery_address) VALUES
    (1, 'Alice Smith', '1985-04-12', '555-0101', '123 Main St, Springfield'),
    (2, 'Bob Johnson', '1990-11-23', '555-0202', '456 Elm St, Shelbyville')
ON CONFLICT DO NOTHING;
SELECT setval('customers_id_seq', (SELECT MAX(id) FROM customers));

INSERT INTO restaurants (id, name, cuisine_type, rating) VALUES
    (1, 'Burger King', 'Fast Food', 4.2),
    (2, 'Sushi Palace', 'Japanese', 4.8),
    (3, 'Pizza Hut', 'Italian', 4.0)
ON CONFLICT DO NOTHING;
SELECT setval('restaurants_id_seq', (SELECT MAX(id) FROM restaurants));

INSERT INTO orders (id, customer_id, restaurant_id, order_status, total_amount, estimated_delivery_time) VALUES
    (1, 1, 2, 'On the way', 45.50, '19:30:00'),
    (2, 2, 1, 'Preparing', 15.75, '20:00:00')
ON CONFLICT DO NOTHING;
SELECT setval('orders_id_seq', (SELECT MAX(id) FROM orders));

INSERT INTO menu_items (id, restaurant_id, item_name, price, is_available) VALUES
    (1, 1, 'Whopper', 5.99, TRUE),
    (2, 1, 'Fries', 2.99, TRUE),
    (3, 2, 'Spicy Tuna Roll', 8.50, TRUE),
    (4, 2, 'Dragon Roll', 12.00, TRUE),
    (5, 3, 'Pepperoni Pizza', 15.00, TRUE)
ON CONFLICT DO NOTHING;
SELECT setval('menu_items_id_seq', (SELECT MAX(id) FROM menu_items));

INSERT INTO order_items (id, customer_id, order_id, menu_item_id, quantity) VALUES
    (1, 1, 1, 3, 2), -- Alice (Customer 1) ordered 2 Spicy Tuna Rolls
    (2, 1, 1, 4, 1), -- Alice ordered 1 Dragon Roll
    (3, 2, 2, 1, 2), -- Bob (Customer 2) ordered 2 Whoppers
    (4, 2, 2, 2, 1)  -- Bob ordered 1 Fries
ON CONFLICT DO NOTHING;
SELECT setval('order_items_id_seq', (SELECT MAX(id) FROM order_items));
