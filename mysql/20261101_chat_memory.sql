-- Additive migration. Select and verify the isolated/staging target database first.
-- Never run automatically on application startup. MySQL 8 / InnoDB / utf8mb4.
CREATE TABLE IF NOT EXISTS staff_chat_session (
  conversation_id CHAR(36) CHARACTER SET ascii PRIMARY KEY,
  owner_id BIGINT NOT NULL,
  title VARCHAR(160) NOT NULL DEFAULT 'New Chat',
  next_sequence BIGINT NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  deleted_at DATETIME(6) NULL,
  INDEX chat_owner_list (owner_id, deleted_at, updated_at, conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS staff_chat_request (
  conversation_id CHAR(36) CHARACTER SET ascii NOT NULL,
  request_id VARCHAR(96) CHARACTER SET ascii NOT NULL,
  fingerprint CHAR(64) CHARACTER SET ascii NOT NULL,
  status VARCHAR(16) NOT NULL,
  response_json JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (conversation_id, request_id),
  INDEX chat_pending (conversation_id, status, request_id),
  FOREIGN KEY (conversation_id) REFERENCES staff_chat_session(conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS staff_chat_message (
  message_id CHAR(36) CHARACTER SET ascii PRIMARY KEY,
  conversation_id CHAR(36) CHARACTER SET ascii NOT NULL,
  sequence_no BIGINT NOT NULL,
  request_id VARCHAR(96) CHARACTER SET ascii NOT NULL,
  role VARCHAR(16) NOT NULL,
  content MEDIUMTEXT NOT NULL,
  metadata_json JSON NULL,
  provenance VARCHAR(40) NOT NULL DEFAULT 'server_original',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY chat_sequence (conversation_id, sequence_no),
  UNIQUE KEY chat_request_role (conversation_id, request_id, role),
  FOREIGN KEY (conversation_id) REFERENCES staff_chat_session(conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Rollback: revert application first. Export these three tables privately.
CREATE TABLE IF NOT EXISTS staff_chat_attachment (
  path VARCHAR(500) CHARACTER SET ascii PRIMARY KEY,
  conversation_id CHAR(36) CHARACTER SET ascii NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES staff_chat_session(conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Dropping tables destroys personal history; only after explicit retention approval:
-- DROP TABLE staff_chat_message; DROP TABLE staff_chat_request; DROP TABLE staff_chat_session;
-- Drop staff_chat_attachment before staff_chat_session as well.
