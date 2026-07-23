-- =============================================================================
-- Voice-Agent Travel Domain Initialization
-- =============================================================================

-- Passengers (Identity Table)
CREATE TABLE IF NOT EXISTS passengers (
    id                SERIAL PRIMARY KEY,
    full_name         VARCHAR(200) NOT NULL,
    date_of_birth     DATE NOT NULL,
    passport_number   VARCHAR(50) UNIQUE
);

-- Flights table
CREATE TABLE IF NOT EXISTS flights (
    id                SERIAL PRIMARY KEY,
    flight_number     VARCHAR(20) UNIQUE NOT NULL,
    origin            VARCHAR(100) NOT NULL,
    destination       VARCHAR(100) NOT NULL,
    departure_time    TIMESTAMPTZ NOT NULL,
    status            VARCHAR(50) DEFAULT 'On Time'
);

-- Bookings table
CREATE TABLE IF NOT EXISTS bookings (
    id                SERIAL PRIMARY KEY,
    passenger_id      INTEGER NOT NULL REFERENCES passengers(id) ON DELETE CASCADE,
    flight_id         INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    seat_number       VARCHAR(10),
    status            VARCHAR(50) DEFAULT 'Confirmed'
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO passengers (id, full_name, date_of_birth, passport_number) VALUES
    (1, 'Alice Smith', '1985-04-12', 'P123456789'),
    (2, 'Bob Johnson', '1990-11-23', 'P987654321'),
    (3, 'Charlie Brown', '1978-08-30', 'P456789123')
ON CONFLICT (id) DO NOTHING;

SELECT setval('passengers_id_seq', (SELECT MAX(id) FROM passengers));

INSERT INTO flights (id, flight_number, origin, destination, departure_time, status) VALUES
    (1, 'AA100', 'New York (JFK)', 'London (LHR)', NOW() + INTERVAL '2 days', 'On Time'),
    (2, 'DL200', 'Los Angeles (LAX)', 'Tokyo (NRT)', NOW() + INTERVAL '5 days', 'Delayed'),
    (3, 'UA300', 'Chicago (ORD)', 'Paris (CDG)', NOW() - INTERVAL '1 day', 'Departed')
ON CONFLICT (id) DO NOTHING;

SELECT setval('flights_id_seq', (SELECT MAX(id) FROM flights));

INSERT INTO bookings (id, passenger_id, flight_id, seat_number, status) VALUES
    (1, 1, 1, '12A', 'Confirmed'),
    (2, 2, 2, '34B', 'Confirmed'),
    (3, 3, 1, '12B', 'Confirmed'),
    (4, 1, 3, '5F', 'Completed')
ON CONFLICT (id) DO NOTHING;

SELECT setval('bookings_id_seq', (SELECT MAX(id) FROM bookings));
