-- Initialize finqueue database and user
CREATE DATABASE IF NOT EXISTS `finqueue` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

CREATE USER IF NOT EXISTS 'finqueue_user'@'%' IDENTIFIED BY 'finqueue_pass';
GRANT ALL PRIVILEGES ON `finqueue`.* TO 'finqueue_user'@'%';
FLUSH PRIVILEGES;
