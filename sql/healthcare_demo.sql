-- =============================================================================
-- Healthcare Voice Agent Demo Database v3
-- Part 1 : Schema
-- =============================================================================

DROP TABLE IF EXISTS doctor_availability CASCADE;
DROP TABLE IF EXISTS lab_results CASCADE;
DROP TABLE IF EXISTS prescriptions CASCADE;
DROP TABLE IF EXISTS appointments CASCADE;
DROP TABLE IF EXISTS doctors CASCADE;
DROP TABLE IF EXISTS clinics CASCADE;
DROP TABLE IF EXISTS patients CASCADE;

-- =============================================================================
-- PATIENTS
-- =============================================================================

CREATE TABLE patients (
    id                  SERIAL PRIMARY KEY,
    full_name           VARCHAR(200) NOT NULL,
    date_of_birth       DATE NOT NULL,
    phone               VARCHAR(20) NOT NULL,
    email               VARCHAR(150),
    insurance_id        VARCHAR(50),
    insurance_provider  VARCHAR(100),
    emergency_contact   VARCHAR(200),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- CLINICS
-- =============================================================================

CREATE TABLE clinics (
    id                      SERIAL PRIMARY KEY,
    clinic_name             VARCHAR(200) NOT NULL,
    address                 TEXT NOT NULL,
    phone                   VARCHAR(20),
    email                   VARCHAR(150),
    working_hours           VARCHAR(150),
    parking_information     TEXT
);

-- =============================================================================
-- DOCTORS
-- =============================================================================

CREATE TABLE doctors (
    id                  SERIAL PRIMARY KEY,
    clinic_id           INTEGER NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    full_name           VARCHAR(200) NOT NULL,
    specialty           VARCHAR(100) NOT NULL,
    department          VARCHAR(100) NOT NULL,
    phone               VARCHAR(20),
    email               VARCHAR(150),
    accepting_new_patients BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- APPOINTMENTS
-- =============================================================================

CREATE TABLE appointments (
    id                      SERIAL PRIMARY KEY,
    patient_id              INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id               INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    clinic_id               INTEGER NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    appointment_date        DATE NOT NULL,
    appointment_time        TIME NOT NULL,
    appointment_duration    INTEGER DEFAULT 30,
    appointment_type        VARCHAR(30) CHECK ( appointment_type IN ('In-Person','Virtual','Phone') ),
    status                  VARCHAR(30) DEFAULT 'Scheduled' CHECK ( status IN ( 'Scheduled', 'Completed', 'Cancelled', 'Rescheduled' ) ),
    reason                  TEXT,
    appointment_notes       TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- PRESCRIPTIONS
-- =============================================================================

CREATE TABLE prescriptions (
    id                      SERIAL PRIMARY KEY,
    patient_id              INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    medication_name         VARCHAR(200) NOT NULL,
    dosage                  VARCHAR(100) NOT NULL,
    frequency               VARCHAR(100),
    refills_remaining       INTEGER DEFAULT 0,
    status                  VARCHAR(30) CHECK ( status IN ( 'Active', 'Completed', 'Expired' ) ),
    prescribed_date         DATE,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- LAB RESULTS
-- =============================================================================

CREATE TABLE lab_results (
    id                      SERIAL PRIMARY KEY,
    patient_id              INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    test_name               VARCHAR(200) NOT NULL,
    result_date             DATE,
    status                  VARCHAR(30) CHECK ( status IN ( 'Pending', 'In Progress', 'Completed', 'Cancelled' ) ),
    result_summary          TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- DOCTOR AVAILABILITY
-- =============================================================================

CREATE TABLE doctor_availability (
    id                      SERIAL PRIMARY KEY,
    doctor_id               INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    available_date          DATE NOT NULL,
    available_time          TIME NOT NULL,
    appointment_type        VARCHAR(30) CHECK ( appointment_type IN ( 'In-Person', 'Virtual', 'Phone' ) ),
    is_available            BOOLEAN DEFAULT TRUE
);

-- =============================================================================
-- PART 2 : MASTER DATA
-- =============================================================================

-- =============================================================================
-- CLINICS
-- =============================================================================

INSERT INTO clinics (clinic_name, address, phone, email, working_hours, parking_information) VALUES

('Sunrise Medical Center', '123 Health Street, Springfield', '+1-555-900-1000', 'info@sunrisemedical.com', 'Monday-Friday 8:00 AM - 6:00 PM', 'Free parking is available in the east parking lot.'),
('Downtown Family Clinic', '450 Main Avenue, Springfield', '+1-555-900-2000', 'contact@downtownclinic.com', 'Monday-Saturday 9:00 AM - 5:00 PM', 'Underground paid parking is available.');

-- =============================================================================
-- DOCTORS
-- =============================================================================

INSERT INTO doctors (clinic_id, full_name, specialty, department, phone, email, accepting_new_patients) VALUES

(1, 'Dr. Sarah Connor', 'Cardiology', 'Heart Center', '+1-555-800-1001', 'sconnor@sunrisemedical.com', TRUE),
(1, 'Dr. John Doe', 'General Practice', 'Primary Care', '+1-555-800-1002', 'jdoe@sunrisemedical.com', TRUE),
(2, 'Dr. Emily Chen', 'Neurology', 'Brain Institute', '+1-555-800-1003', 'echen@downtownclinic.com', FALSE),
(2, 'Dr. Michael Adams', 'Orthopedics', 'Bone & Joint Center', '+1-555-800-1004', 'madams@downtownclinic.com', TRUE);

-- =============================================================================
-- PATIENTS
-- =============================================================================

INSERT INTO patients (full_name, date_of_birth, phone, email, insurance_id, insurance_provider, emergency_contact) VALUES

('Alice Smith', '1985-04-12', '+1-555-111-2222', 'alice.smith@email.com', 'INS-999-123', 'Blue Cross Health', 'Robert Smith (+1-555-100-2000)'),
('Bob Johnson', '1990-11-23', '+1-555-333-4444', 'bob.johnson@email.com', 'INS-888-456', 'United Healthcare', 'Emma Johnson (+1-555-300-4000)'),
('Charlie Brown', '1975-08-05', '+1-555-555-6666', 'charlie.brown@email.com', 'INS-777-789', 'Aetna', 'Linda Brown (+1-555-500-6000)'),
('Sophia Wilson', '1988-01-17', '+1-555-777-8888', 'sophia.w@email.com', 'INS-444-888', 'Blue Shield', 'James Wilson (+1-555-777-9999)'),
('David Miller', '1993-09-10', '+1-555-888-9999', 'david.m@email.com', 'INS-555-222', 'Cigna', 'Olivia Miller (+1-555-123-1234)');

-- =============================================================================
-- PART 3 : APPOINTMENTS
-- =============================================================================

INSERT INTO appointments (patient_id, doctor_id, clinic_id, appointment_date, appointment_time, appointment_duration, appointment_type, status, reason, appointment_notes) VALUES

-- ===========================================================
-- Alice Smith (Main Demo Patient)
-- ===========================================================

(1, 1, 1, CURRENT_DATE + INTERVAL '5 day', '10:30', 30, 'In-Person', 'Scheduled', 'Routine cholesterol follow-up', 'Please arrive 15 minutes early and bring your insurance card.'),
(1, 2, 1, CURRENT_DATE - INTERVAL '90 day', '09:00', 20, 'In-Person', 'Completed', 'Annual physical examination', 'Patient advised to maintain regular exercise.'),
(1, 1, 1, CURRENT_DATE + INTERVAL '35 day', '02:00 PM', 30, 'Virtual', 'Scheduled', 'Medication review', 'Virtual consultation link will be emailed 24 hours before appointment.'),
-- ===========================================================
-- Bob Johnson
-- ===========================================================

(2, 3, 2, CURRENT_DATE + INTERVAL '8 day', '11:15', 45, 'In-Person', 'Scheduled', 'Migraine consultation', 'Please bring previous MRI reports.'),
(2, 3, 2, CURRENT_DATE - INTERVAL '40 day', '03:00 PM', 45, 'In-Person', 'Completed', 'Neurology follow-up', 'Continue prescribed medication.'),
-- ===========================================================
-- Charlie Brown
-- ===========================================================

(3, 4, 2, CURRENT_DATE - INTERVAL '120 day', '01:00 PM', 30, 'In-Person', 'Completed', 'Knee pain consultation', 'Recommended physiotherapy.'),
-- ===========================================================
-- Sophia Wilson
-- ===========================================================

(4, 2, 1, CURRENT_DATE + INTERVAL '12 day', '09:45', 30, 'Phone', 'Scheduled', 'General health consultation', 'Doctor will call the registered phone number.'),
-- ===========================================================
-- David Miller
-- ===========================================================

(5, 4, 2, CURRENT_DATE + INTERVAL '18 day', '04:00 PM', 45, 'In-Person', 'Cancelled', 'Orthopedic consultation', 'Patient requested cancellation.');

-- =============================================================================
-- PRESCRIPTIONS
-- =============================================================================

INSERT INTO prescriptions (patient_id, medication_name, dosage, frequency, refills_remaining, status, prescribed_date) VALUES

-- Alice

(1, 'Atorvastatin', '20 mg', 'Once Daily', 2, 'Active', CURRENT_DATE - INTERVAL '60 day'),
(1, 'Aspirin', '81 mg', 'Once Daily', 5, 'Active', CURRENT_DATE - INTERVAL '120 day'),
(1, 'Vitamin D', '1000 IU', 'Once Daily', 0, 'Completed', CURRENT_DATE - INTERVAL '200 day'),
-- Bob

(2, 'Sumatriptan', '50 mg', 'As Needed', 1, 'Active', CURRENT_DATE - INTERVAL '20 day'),
(2, 'Ibuprofen', '400 mg', 'Twice Daily', 0, 'Expired', CURRENT_DATE - INTERVAL '300 day'),
-- Charlie

(3, 'Calcium Supplement', '500 mg', 'Once Daily', 3, 'Active', CURRENT_DATE - INTERVAL '30 day'),
-- Sophia

(4, 'Metformin', '500 mg', 'Twice Daily', 4, 'Active', CURRENT_DATE - INTERVAL '40 day'),
-- David

(5, 'Diclofenac', '50 mg', 'Twice Daily', 1, 'Active', CURRENT_DATE - INTERVAL '10 day');

-- =============================================================================
-- LAB RESULTS
-- =============================================================================

INSERT INTO lab_results (patient_id, test_name, result_date, status, result_summary) VALUES

-- Alice

(1, 'Lipid Panel', NULL, 'Pending', 'Laboratory processing is in progress.'),
(1, 'Complete Blood Count', CURRENT_DATE - INTERVAL '80 day', 'Completed', 'Blood counts are within normal limits.'),
(1, 'Liver Function Test', CURRENT_DATE - INTERVAL '150 day', 'Completed', 'No abnormal liver function detected.'),
-- Bob

(2, 'MRI Brain', CURRENT_DATE - INTERVAL '25 day', 'Completed', 'No acute neurological abnormalities.'),
(2, 'Vitamin B12', NULL, 'Pending', 'Sample received and awaiting analysis.'),
-- Charlie

(3, 'Bone Density Scan', CURRENT_DATE -INTERVAL '100 day', 'Completed', 'Mild reduction in bone density observed.'),
-- Sophia

(4, 'Blood Glucose', CURRENT_DATE -INTERVAL '15 day', 'Completed', 'Blood sugar remains under good control.'),
-- David

(5, 'Knee X-Ray', NULL, 'In Progress', 'Radiology department is reviewing images.');

-- =============================================================================
-- DOCTOR AVAILABILITY
-- =============================================================================

INSERT INTO doctor_availability (doctor_id, available_date, available_time, appointment_type, is_available) VALUES

(1,CURRENT_DATE + INTERVAL '1 day','09:00','In-Person',TRUE),
(1,CURRENT_DATE + INTERVAL '1 day','10:00','In-Person',TRUE),
(1,CURRENT_DATE + INTERVAL '1 day','11:00','Virtual',TRUE),
(1,CURRENT_DATE + INTERVAL '2 day','09:00','In-Person',TRUE),
(1,CURRENT_DATE + INTERVAL '2 day','10:00','Virtual',TRUE),
(2,CURRENT_DATE + INTERVAL '3 day','02:00 PM','Phone',TRUE),
(2,CURRENT_DATE + INTERVAL '3 day','03:00 PM','In-Person',TRUE),
(3,CURRENT_DATE + INTERVAL '4 day','09:30','In-Person',TRUE),
(3,CURRENT_DATE + INTERVAL '4 day','10:30','In-Person',FALSE),
(4,CURRENT_DATE + INTERVAL '5 day','01:00 PM','In-Person',TRUE),
(4,CURRENT_DATE + INTERVAL '5 day','02:00 PM','In-Person',TRUE);

-- =============================================================================
-- PART 4 : INDEXES
-- =============================================================================

-- Patients
CREATE INDEX idx_patients_name ON patients(full_name);

CREATE INDEX idx_patients_dob ON patients(date_of_birth);

-- Doctors
CREATE INDEX idx_doctors_specialty ON doctors(specialty);

CREATE INDEX idx_doctors_department ON doctors(department);

CREATE INDEX idx_doctors_clinic ON doctors(clinic_id);

-- Appointments
CREATE INDEX idx_appointments_patient ON appointments(patient_id);

CREATE INDEX idx_appointments_doctor ON appointments(doctor_id);

CREATE INDEX idx_appointments_date ON appointments(appointment_date);

CREATE INDEX idx_appointments_status ON appointments(status);

-- Prescriptions
CREATE INDEX idx_prescriptions_patient ON prescriptions(patient_id);

CREATE INDEX idx_prescriptions_status ON prescriptions(status);

-- Lab Results
CREATE INDEX idx_lab_results_patient ON lab_results(patient_id);

CREATE INDEX idx_lab_results_status ON lab_results(status);

-- Doctor Availability
CREATE INDEX idx_availability_doctor ON doctor_availability(doctor_id);

CREATE INDEX idx_availability_date ON doctor_availability(available_date);

CREATE INDEX idx_availability_available ON doctor_availability(is_available);