USE railway;

-- =========================================================
-- ESCALATION TABLE
-- Stores AI questions that need Team Lead / Manager review
-- =========================================================

CREATE TABLE IF NOT EXISTS escalation (
    escalation_id INT AUTO_INCREMENT PRIMARY KEY,

    -- Staff question and AI response
    question TEXT NOT NULL,
    ai_answer TEXT NULL,
    ai_score DECIMAL(6,4) DEFAULT 0,
    ai_source VARCHAR(100) NULL,

    -- Team Lead / Manager manual answer
    manual_answer TEXT NULL,

    -- User references (optional)
    asked_by INT NULL,
    handled_by INT NULL,

    -- Escalation status
    status ENUM('pending', 'reviewing', 'resolved') 
        NOT NULL DEFAULT 'pending',

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
        ON UPDATE CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,

    -- Index (improves performance)
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),

    -- Foreign keys (only if users table exists)
    CONSTRAINT fk_escalation_asked_by
        FOREIGN KEY (asked_by) REFERENCES users(user_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_escalation_handled_by
        FOREIGN KEY (handled_by) REFERENCES users(user_id)
        ON DELETE SET NULL
);