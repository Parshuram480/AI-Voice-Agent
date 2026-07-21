-- =============================================================================
-- Healthcare Voice Agent Demo Database Initialization
-- Run this script against your PostgreSQL database to create the schema
-- and insert sample data for testing.
--
-- Usage:  psql -U postgres -d postgres -c "CREATE DATABASE healthcare_demo;"
--         psql -U postgres -d healthcare_demo -f sql/healthcare_demo.sql
-- =============================================================================

-- Patients table (Identity table)
CREATE TABLE IF NOT EXISTS patients (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE NOT NULL,
    phone           VARCHAR(20),
    insurance_id    VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Doctors table
CREATE TABLE IF NOT EXISTS doctors (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(200) NOT NULL,
    specialty       VARCHAR(100) NOT NULL,
    department      VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Appointments table
CREATE TABLE IF NOT EXISTS appointments (
    id                  SERIAL PRIMARY KEY,
    patient_id          INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id           INTEGER NOT NULL REFERENCES doctors(id) ON DELETE SET NULL,
    appointment_date    DATE NOT NULL,
    appointment_time    TIME NOT NULL,
    status              VARCHAR(50) NOT NULL DEFAULT 'Scheduled',
    reason              TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Prescriptions table
CREATE TABLE IF NOT EXISTS prescriptions (
    id                  SERIAL PRIMARY KEY,
    patient_id          INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    medication_name     VARCHAR(200) NOT NULL,
    dosage              VARCHAR(100) NOT NULL,
    refills_remaining   INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Lab Results table
CREATE TABLE IF NOT EXISTS lab_results (
    id                  SERIAL PRIMARY KEY,
    patient_id          INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    test_name           VARCHAR(200) NOT NULL,
    result_date         DATE,
    status              VARCHAR(50) NOT NULL DEFAULT 'Pending',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);



-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO patients (id, full_name, date_of_birth, phone, insurance_id) VALUES
    (1, 'Alice Smith', '1985-04-12', '+15551112222', 'INS-999-123'),
    (2, 'Bob Johnson', '1990-11-23', '+15553334444', 'INS-888-456'),
    (3, 'Charlie Brown', '1975-08-05', '+15555556666', 'INS-777-789')
ON CONFLICT DO NOTHING;
-- Reset sequence
SELECT setval('patients_id_seq', (SELECT MAX(id) FROM patients));

INSERT INTO doctors (id, full_name, specialty, department) VALUES
    (1, 'Dr. Sarah Connor', 'Cardiology', 'Heart Center'),
    (2, 'Dr. John Doe', 'General Practice', 'Primary Care'),
    (3, 'Dr. Emily Chen', 'Neurology', 'Brain Institute')
ON CONFLICT DO NOTHING;
SELECT setval('doctors_id_seq', (SELECT MAX(id) FROM doctors));

INSERT INTO appointments (id, patient_id, doctor_id, appointment_date, appointment_time, status, reason) VALUES
    (1, 1, 1, '2026-08-15', '10:00:00', 'Scheduled', 'Routine checkup'),
    (2, 1, 2, '2026-07-20', '14:30:00', 'Completed', 'Flu symptoms'),
    (3, 2, 3, '2026-09-05', '09:15:00', 'Scheduled', 'Migraine consultation')
ON CONFLICT DO NOTHING;
SELECT setval('appointments_id_seq', (SELECT MAX(id) FROM appointments));

INSERT INTO prescriptions (id, patient_id, medication_name, dosage, refills_remaining) VALUES
    (1, 1, 'Lisinopril', '10mg daily', 2),
    (2, 1, 'Atorvastatin', '20mg daily', 0),
    (3, 2, 'Sumatriptan', '50mg as needed', 5)
ON CONFLICT DO NOTHING;
SELECT setval('prescriptions_id_seq', (SELECT MAX(id) FROM prescriptions));

INSERT INTO lab_results (id, patient_id, test_name, result_date, status) VALUES
    (1, 1, 'Complete Blood Count', '2026-07-15', 'Completed'),
    (2, 1, 'Lipid Panel', NULL, 'Pending'),
    (3, 2, 'MRI Brain', '2026-07-10', 'Completed')
ON CONFLICT DO NOTHING;
SELECT setval('lab_results_id_seq', (SELECT MAX(id) FROM lab_results));
