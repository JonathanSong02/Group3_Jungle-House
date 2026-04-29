#------CREATE QUIZ TABLE---------
USE railway;

CREATE TABLE IF NOT EXISTS quiz (
    quiz_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT NULL,
    category VARCHAR(100) NULL,
    created_by INT NULL,
    status ENUM('active', 'inactive') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_quiz_created_by
        FOREIGN KEY (created_by) REFERENCES users(user_id)
        ON DELETE SET NULL
);

SHOW TABLES;

#------CREATE MULTIPLE QUESTION TABLE FOR QUIZ---------
CREATE TABLE IF NOT EXISTS quiz_question (
    question_id INT AUTO_INCREMENT PRIMARY KEY,
    quiz_id INT NOT NULL,
    question_text TEXT NOT NULL,
    option_a VARCHAR(255) NOT NULL,
    option_b VARCHAR(255) NOT NULL,
    option_c VARCHAR(255) NOT NULL,
    option_d VARCHAR(255) NOT NULL,
    correct_option ENUM('A', 'B', 'C', 'D') NOT NULL,
    explanation TEXT NULL,
    points INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_quiz_question_quiz
        FOREIGN KEY (quiz_id) REFERENCES quiz(quiz_id)
        ON DELETE CASCADE
);

#-----------STORE STAFF QUIZ ATTEMPT
CREATE TABLE IF NOT EXISTS quiz_result (
    result_id INT AUTO_INCREMENT PRIMARY KEY,
    quiz_id INT NOT NULL,
    user_id INT NOT NULL,
    score INT DEFAULT 0,
    total_questions INT DEFAULT 0,
    percentage DECIMAL(5,2) DEFAULT 0,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_quiz_result_quiz
        FOREIGN KEY (quiz_id) REFERENCES quiz(quiz_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_quiz_result_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE
);




#--------------TEST QUESTION-------------
USE railway;

INSERT INTO quiz (title, description, category, created_by, status)
VALUES (
    'Pre-Official Interview Training',
    'Basic training quiz for new Jungle House staff before official interview.',
    'Training',
    NULL,
    'active'
);


#-----CHECK QUIZ ID------
SELECT * FROM quiz;

#-----INSERT QUESTION--------
INSERT INTO quiz_question 
(quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation, points)
VALUES
(
    1,
    'What should staff do before starting work?',
    'Clock in',
    'Go home',
    'Ignore SOP',
    'Close the shop',
    'A',
    'Staff should clock in before starting work.',
    1
);

#-----CHECK QUESTION INSERTED------
SELECT * FROM quiz_question;