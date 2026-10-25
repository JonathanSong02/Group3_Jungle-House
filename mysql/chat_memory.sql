-- Apply once to the selected LOCAL/test database, then production after review.
-- Additive migration; does not replace escalation or delete existing data.
CREATE TABLE IF NOT EXISTS chat_conversations (
    chat_id VARCHAR(64) PRIMARY KEY,
    owner_id INT NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT 'New Chat',
    latest_message_id VARCHAR(64) NULL,
    summary_json LONGTEXT NULL,
    hidden TINYINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX chat_owner (owner_id, hidden, updated_at)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS chat_turns (
    message_id VARCHAR(64) PRIMARY KEY,
    chat_id VARCHAR(64) NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    sequence_no BIGINT NOT NULL,
    original_question LONGTEXT NOT NULL,
    attachment_json LONGTEXT NULL,
    resolution_json LONGTEXT NULL,
    response_json LONGTEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    lease_id VARCHAR(64) NOT NULL,
    lease_until DOUBLE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY chat_request (chat_id, request_id),
    UNIQUE KEY chat_sequence (chat_id, sequence_no),
    FOREIGN KEY (chat_id) REFERENCES chat_conversations(chat_id)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS chat_escalation_context (
    issue_id VARCHAR(64) PRIMARY KEY,
    escalation_id INT NOT NULL,
    chat_id VARCHAR(64) NOT NULL,
    latest_message_id VARCHAR(64) NOT NULL,
    original_question LONGTEXT NOT NULL,
    resolved_question LONGTEXT NOT NULL,
    reason TEXT NOT NULL,
    transcript_json LONGTEXT NOT NULL,
    background_json LONGTEXT NOT NULL,
    UNIQUE KEY chat_ticket (escalation_id),
    FOREIGN KEY (chat_id) REFERENCES chat_conversations(chat_id)
) CHARACTER SET utf8mb4;
