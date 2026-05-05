USE railway;

CREATE TABLE IF NOT EXISTS review_queue (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    escalation_id INT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    submitted_by INT NULL,
    reviewed_by INT NULL,
    status ENUM('pending', 'approved', 'rejected', 'published') NOT NULL DEFAULT 'pending',
    reviewer_comment TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP NULL,
    published_at TIMESTAMP NULL,

    FOREIGN KEY (escalation_id) REFERENCES escalation(escalation_id),
    FOREIGN KEY (submitted_by) REFERENCES users(user_id),
    FOREIGN KEY (reviewed_by) REFERENCES users(user_id)
);