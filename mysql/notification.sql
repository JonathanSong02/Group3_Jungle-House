CREATE TABLE notification (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255),
    message TEXT,
    type ENUM('escalation','review','announcement','system'),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS notification (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type ENUM('escalation','review','announcement','system') NOT NULL DEFAULT 'system',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);


INSERT INTO notification (user_id, title, message, type, is_read)
VALUES
(2, 'New Announcement', 'Hari Raya promotion briefing has been updated.', 'announcement', FALSE),
(2, 'Escalation Alert', 'A question requires team lead review.', 'escalation', FALSE),
(2, 'System Reminder', 'Please review your training progress.', 'system', TRUE);

SELECT user_id, full_name, email FROM users;