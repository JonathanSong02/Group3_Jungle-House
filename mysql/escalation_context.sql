-- OPTIONAL additive migration for issue-specific escalation excerpts.
-- Review and select your isolated/target database explicitly before running.
-- No USE, data updates, credentials, or automatic execution by the application.
-- The existing escalation.escalation_id must be an INT primary key (InnoDB).
CREATE TABLE IF NOT EXISTS escalation_context (
    escalation_id INT NOT NULL PRIMARY KEY,
    conversation_id VARCHAR(96) NOT NULL,
    issue_id VARCHAR(96) NOT NULL,
    context_json MEDIUMTEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_escalation_context_ticket
        FOREIGN KEY (escalation_id) REFERENCES escalation(escalation_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
