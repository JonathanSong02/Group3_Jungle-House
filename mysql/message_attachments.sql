-- Run against the intended application database before deploying this feature.
-- No USE statement or existing data changes. Files use the backend persistent volume.
CREATE TABLE IF NOT EXISTS message_attachments (
    attachment_id CHAR(64) PRIMARY KEY,
    message_id INT NOT NULL,
    storage_name VARCHAR(100) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    byte_size INT UNSIGNED NOT NULL,
    INDEX idx_message_attachments_message (message_id)
);
