-- Minimal bootstrap for MariaDB: create database and application user.
CREATE DATABASE IF NOT EXISTS autonomy CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'autonomy_user'@'%' IDENTIFIED BY 'Autonomy@2025';
GRANT ALL PRIVILEGES ON autonomy.* TO 'autonomy_user'@'%';
GRANT ALL PRIVILEGES ON *.* TO 'autonomy_user'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
