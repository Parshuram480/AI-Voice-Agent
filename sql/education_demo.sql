-- =============================================================================
-- Voice-Agent Education Domain Initialization
-- =============================================================================

-- Students (Identity Table)
CREATE TABLE IF NOT EXISTS students (
    id                SERIAL PRIMARY KEY,
    full_name         VARCHAR(200) NOT NULL,
    date_of_birth     DATE NOT NULL,
    enrollment_year   INTEGER NOT NULL,
    major             VARCHAR(100)
);

-- Courses table
CREATE TABLE IF NOT EXISTS courses (
    id                SERIAL PRIMARY KEY,
    course_name       VARCHAR(150) NOT NULL,
    credits           INTEGER NOT NULL,
    instructor        VARCHAR(100)
);

-- Enrollments table
CREATE TABLE IF NOT EXISTS enrollments (
    id                SERIAL PRIMARY KEY,
    student_id        INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id         INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    semester          VARCHAR(50) NOT NULL,
    grade             VARCHAR(5)
);

-- Tuition Fees table
CREATE TABLE IF NOT EXISTS tuition_fees (
    id                SERIAL PRIMARY KEY,
    student_id        INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    amount_due        DECIMAL(10, 2) NOT NULL,
    amount_paid       DECIMAL(10, 2) DEFAULT 0.00,
    status            VARCHAR(50) DEFAULT 'Unpaid'
);

-- =============================================================================
-- Sample Data
-- =============================================================================

INSERT INTO students (id, full_name, date_of_birth, enrollment_year, major) VALUES
    (1, 'Alice Smith', '2002-04-12', 2024, 'Computer Science'),
    (2, 'Bob Johnson', '2001-11-23', 2023, 'Business Administration'),
    (3, 'Charlie Brown', '2003-08-30', 2025, 'Psychology')
ON CONFLICT (id) DO NOTHING;

SELECT setval('students_id_seq', (SELECT MAX(id) FROM students));

INSERT INTO courses (id, course_name, credits, instructor) VALUES
    (1, 'Introduction to Programming', 3, 'Dr. Alan Turing'),
    (2, 'Microeconomics', 3, 'Prof. Adam Smith'),
    (3, 'Cognitive Psychology', 4, 'Dr. Sigmund Freud')
ON CONFLICT (id) DO NOTHING;

SELECT setval('courses_id_seq', (SELECT MAX(id) FROM courses));

INSERT INTO enrollments (id, student_id, course_id, semester, grade) VALUES
    (1, 1, 1, 'Fall 2026', 'A'),
    (2, 1, 2, 'Fall 2026', 'B+'),
    (3, 2, 2, 'Fall 2026', 'A-'),
    (4, 3, 3, 'Fall 2026', 'In Progress')
ON CONFLICT (id) DO NOTHING;

SELECT setval('enrollments_id_seq', (SELECT MAX(id) FROM enrollments));

INSERT INTO tuition_fees (id, student_id, amount_due, amount_paid, status) VALUES
    (1, 1, 15000.00, 15000.00, 'Paid'),
    (2, 2, 15000.00, 5000.00, 'Partial'),
    (3, 3, 14000.00, 0.00, 'Unpaid')
ON CONFLICT (id) DO NOTHING;

SELECT setval('tuition_fees_id_seq', (SELECT MAX(id) FROM tuition_fees));
