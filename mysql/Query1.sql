
USE railway;
CREATE TABLE roles (
    role_id INT AUTO_INCREMENT PRIMARY KEY,
    role_name VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id INT NOT NULL,
    status ENUM('active', 'inactive') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE registration_keys (
    key_id INT AUTO_INCREMENT PRIMARY KEY,
    key_code VARCHAR(100) NOT NULL UNIQUE,
    allowed_role_id INT NOT NULL,
    created_by INT NOT NULL,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    used_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    FOREIGN KEY (allowed_role_id) REFERENCES roles(role_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id),
    FOREIGN KEY (used_by) REFERENCES users(user_id)
);

CREATE TABLE login_history (
    login_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    login_status ENUM('success', 'failed') NOT NULL,
    ip_address VARCHAR(45),
    device_info VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

INSERT INTO roles (role_name)
VALUES ('manager'), ('teamlead'), ('staff');

INSERT INTO users (full_name, email, password_hash, role_id, status)
VALUES (
    'System Manager',
    'manager@junglehouse.com',
    'pbkdf2:sha256:600000$demo$replace_with_real_hash',
    1,
    'active'
);

INSERT INTO registration_keys (key_code, allowed_role_id, created_by, expires_at)
VALUES
('JH-STAFF-001', 3, 1, '2026-12-31 23:59:59'),
('JH-LEAD-001', 2, 1, '2026-12-31 23:59:59');




SHOW TABLES;

SELECT * FROM roles;

SELECT * FROM registration_keys;



SELECT * FROM users;



SELECT
    lh.login_id,
    u.full_name,
    u.email,
    lh.login_status,
    lh.login_time,
    lh.ip_address,
    lh.device_info
FROM login_history lh
JOIN users u ON lh.user_id = u.user_id
ORDER BY lh.login_time DESC;