-- =============================================================================
-- Voice-Agent HR Domain Initialization
-- =============================================================================

-- Employees (Identity Table)
CREATE TABLE IF NOT EXISTS employees (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,
    department      VARCHAR(100),
    role            VARCHAR(100),
    hire_date       DATE NOT NULL
);

-- Leave Requests table
CREATE TABLE IF NOT EXISTS leave_requests (
    id               SERIAL PRIMARY KEY,
    employee_id      INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    start_date       DATE NOT NULL,
    end_date         DATE NOT NULL,
    leave_type       VARCHAR(50) NOT NULL,
    status           VARCHAR(50) DEFAULT 'Pending'
);

-- Payroll table
CREATE TABLE IF NOT EXISTS payroll (
    id               SERIAL PRIMARY KEY,
    employee_id      INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    month            VARCHAR(20) NOT NULL,
    net_pay          DECIMAL(10, 2) NOT NULL,
    payment_status   VARCHAR(50) DEFAULT 'Paid'
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO employees (id, full_name, date_of_birth, department, role, hire_date) VALUES
    (1, 'Alice Smith', '1985-04-12', 'Engineering', 'Senior Developer', '2020-03-15'),
    (2, 'Bob Johnson', '1990-11-23', 'Sales', 'Account Executive', '2021-06-01'),
    (3, 'Charlie Brown', '1978-08-30', 'HR', 'HR Manager', '2019-01-10')
ON CONFLICT (id) DO NOTHING;

SELECT setval('employees_id_seq', (SELECT MAX(id) FROM employees));

INSERT INTO leave_requests (id, employee_id, start_date, end_date, leave_type, status) VALUES
    (1, 1, CURRENT_DATE + INTERVAL '10 days', CURRENT_DATE + INTERVAL '14 days', 'Vacation', 'Approved'),
    (2, 2, CURRENT_DATE - INTERVAL '2 days', CURRENT_DATE, 'Sick Leave', 'Approved'),
    (3, 1, CURRENT_DATE + INTERVAL '45 days', CURRENT_DATE + INTERVAL '46 days', 'Personal Time', 'Pending')
ON CONFLICT (id) DO NOTHING;

SELECT setval('leave_requests_id_seq', (SELECT MAX(id) FROM leave_requests));

INSERT INTO payroll (id, employee_id, month, net_pay, payment_status) VALUES
    (1, 1, 'July 2026', 7500.00, 'Paid'),
    (2, 2, 'July 2026', 4200.00, 'Paid'),
    (3, 3, 'July 2026', 5800.00, 'Paid'),
    (4, 1, 'August 2026', 7500.00, 'Processing')
ON CONFLICT (id) DO NOTHING;

SELECT setval('payroll_id_seq', (SELECT MAX(id) FROM payroll));
