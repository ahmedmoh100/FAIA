-- =============================================
--  FAIA Chat System — Complete Database Schema
--  Engine: MySQL / MariaDB (tested on MariaDB 10.4+)
--  Charset: utf8mb4
--
--  SETUP:
--    1. Run this file once to create all tables
--    2. Create your admin user via the API after setup (see bottom of file)
-- =============================================

CREATE DATABASE IF NOT EXISTS faia_chat_system;
USE faia_chat_system;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =============================================
-- 1. USERS
-- =============================================
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `user_id`       int(11)      NOT NULL AUTO_INCREMENT,
  `username`      varchar(100) NOT NULL,
  `email`         varchar(150) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `password_salt` varchar(32)  NOT NULL,
  `role`   enum('ADMIN','PROFESSOR','STUDENT') DEFAULT 'STUDENT',
  `status` enum('ACTIVE','DEACTIVATED','SUSPENDED') DEFAULT 'ACTIVE',
  `created_at`    datetime     DEFAULT CURRENT_TIMESTAMP,
  `last_login`    datetime     DEFAULT NULL,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `ix_users_username` (`username`),
  UNIQUE KEY `ix_users_email`    (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 2. SESSIONS
-- =============================================
DROP TABLE IF EXISTS `sessions`;
CREATE TABLE `sessions` (
  `session_id`      int(11)     NOT NULL AUTO_INCREMENT,
  `user_id`         int(11)     NOT NULL,
  `login_time`      datetime    DEFAULT CURRENT_TIMESTAMP,
  `logout_time`     datetime    DEFAULT NULL,
  `ip_address`      varchar(45) DEFAULT NULL,
  `current_chat_id` int(11)     DEFAULT NULL,
  `last_activity`   timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status`          varchar(20) DEFAULT 'active',
  PRIMARY KEY (`session_id`),
  KEY `ix_sessions_user_id`         (`user_id`),
  KEY `ix_sessions_current_chat_id` (`current_chat_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 3. CHATS
-- =============================================
DROP TABLE IF EXISTS `chats`;
CREATE TABLE `chats` (
  `chat_id`    int(11)      NOT NULL AUTO_INCREMENT,
  `user_id`    int(11)      NOT NULL,
  `title`      varchar(255) DEFAULT NULL,
  `created_at` datetime     DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `session_id` int(11)      DEFAULT NULL,
  `is_active`  tinyint(1)   DEFAULT 1,
  PRIMARY KEY (`chat_id`),
  KEY `ix_chats_user_id`    (`user_id`),
  KEY `ix_chats_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 4. MESSAGES
-- =============================================
DROP TABLE IF EXISTS `messages`;
CREATE TABLE `messages` (
  `message_id`  int(11)              NOT NULL AUTO_INCREMENT,
  `chat_id`     int(11)              NOT NULL,
  `sender`      enum('user','ai')    NOT NULL,
  `content`     text                 NOT NULL,
  `token_count` int(11)              DEFAULT 0,
  `created_at`  datetime             DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`message_id`),
  KEY `ix_messages_chat_id` (`chat_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 5. AUDIT LOGS
-- =============================================
DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (
  `log_id`       int(11)      NOT NULL AUTO_INCREMENT,
  `admin_id`     int(11)      DEFAULT NULL,
  `action`       varchar(255) NOT NULL,
  `target_id`    int(11)      DEFAULT NULL,
  `target_table` varchar(100) DEFAULT NULL,
  `details`      text         DEFAULT NULL,
  `timestamp`    datetime     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`log_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 6. TOKEN LIMITS
-- =============================================
DROP TABLE IF EXISTS `token_limits`;
CREATE TABLE `token_limits` (
  `limit_id`    int(11)  NOT NULL AUTO_INCREMENT,
  `user_id`     int(11)  NOT NULL,
  `max_tokens`  int(11)  DEFAULT 100000,
  `used_tokens` int(11)  DEFAULT 0,
  `period_start` datetime DEFAULT CURRENT_TIMESTAMP,
  `period_end`   datetime DEFAULT NULL,
  PRIMARY KEY (`limit_id`),
  KEY `ix_token_limits_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 7. COURSE MATERIALS  (RAG document storage)
-- =============================================
DROP TABLE IF EXISTS `course_materials`;
CREATE TABLE `course_materials` (
  `material_id`       int(11)      NOT NULL AUTO_INCREMENT,
  `filename`          varchar(255) DEFAULT NULL,
  `original_filename` varchar(255) DEFAULT NULL,
  `file_path`         varchar(500) DEFAULT NULL,
  `file_type`         varchar(50)  DEFAULT NULL,
  `file_size`         bigint(20)   DEFAULT NULL,
  `course_name`       varchar(255) DEFAULT NULL,
  `course_code`       varchar(100) DEFAULT NULL,
  `uploaded_by`       int(11)      DEFAULT NULL,
  `upload_date`       timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `processed`         tinyint(1)   DEFAULT 0,
  `status`            varchar(50)  DEFAULT 'pending',
  `chunk_count`       int(11)      DEFAULT 0,
  PRIMARY KEY (`material_id`),
  KEY `ix_course_materials_course_code` (`course_code`),
  KEY `ix_course_materials_uploaded_by` (`uploaded_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 8. COURSES
-- =============================================
DROP TABLE IF EXISTS `courses`;
CREATE TABLE `courses` (
  `course_id`     int(11)      NOT NULL AUTO_INCREMENT,
  `course_code`   varchar(50)  NOT NULL,
  `course_name`   varchar(255) NOT NULL,
  `description`   text         DEFAULT NULL,
  `instructor_id` int(11)      DEFAULT NULL,
  `created_at`    datetime     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`course_id`),
  UNIQUE KEY `ix_courses_code` (`course_code`),
  KEY `ix_courses_instructor` (`instructor_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 9. DOCUMENT CHUNKS  (RAG chunked content)
-- =============================================
DROP TABLE IF EXISTS `document_chunks`;
CREATE TABLE `document_chunks` (
  `chunk_id`    int(11)      NOT NULL AUTO_INCREMENT,
  `material_id` int(11)      NOT NULL,
  `chunk_index` int(11)      NOT NULL,
  `content`     text         NOT NULL,
  `created_at`  datetime     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`chunk_id`),
  KEY `ix_document_chunks_material` (`material_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 10. UPLOADED FILES  (per-user file uploads)
-- =============================================
DROP TABLE IF EXISTS `uploaded_files`;
CREATE TABLE `uploaded_files` (
  `file_id`     int(11)     NOT NULL AUTO_INCREMENT,
  `user_id`     int(11)     NOT NULL,
  `chat_id`     int(11)     DEFAULT NULL,
  `file_name`   varchar(255) NOT NULL,
  `file_path`   varchar(500) NOT NULL,
  `file_type`   varchar(50)  DEFAULT NULL,
  `upload_time` datetime    DEFAULT CURRENT_TIMESTAMP,
  `status`      varchar(50) DEFAULT 'validated',
  PRIMARY KEY (`file_id`),
  KEY `ix_uploaded_files_user` (`user_id`),
  KEY `ix_uploaded_files_chat` (`chat_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 11. PASSWORD RESET TOKENS
-- =============================================
DROP TABLE IF EXISTS `password_reset_tokens`;
CREATE TABLE `password_reset_tokens` (
  `token_id`   int(11)      NOT NULL AUTO_INCREMENT,
  `user_id`    int(11)      NOT NULL,
  `token`      varchar(255) NOT NULL,
  `expires_at` datetime     NOT NULL,
  `used`       tinyint(1)   DEFAULT 0,
  `created_at` datetime     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`token_id`),
  UNIQUE KEY `ix_reset_token` (`token`),
  KEY `ix_reset_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 12. MODERATION FLAGS
-- =============================================
DROP TABLE IF EXISTS `moderation_flags`;
CREATE TABLE `moderation_flags` (
  `flag_id`     int(11)     NOT NULL AUTO_INCREMENT,
  `target_type` varchar(50) NOT NULL,
  `target_id`   int(11)     DEFAULT NULL,
  `reporter_id` int(11)     DEFAULT NULL,
  `reason`      text        DEFAULT NULL,
  `status`      varchar(50) DEFAULT 'new',
  `created_at`  datetime    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`flag_id`),
  KEY `ix_mod_flags_target` (`target_type`, `target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 13. MODERATION REPORTS
-- =============================================
DROP TABLE IF EXISTS `moderation_reports`;
CREATE TABLE `moderation_reports` (
  `report_id`   int(11)     NOT NULL AUTO_INCREMENT,
  `message_id`  int(11)     NOT NULL,
  `reported_by` int(11)     NOT NULL,
  `reason`      text        NOT NULL,
  `status`      enum('pending','validated','resolved') DEFAULT 'pending',
  `created_at`  datetime    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`report_id`),
  KEY `ix_mod_reports_message` (`message_id`),
  KEY `ix_mod_reports_reporter` (`reported_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 14. MODERATION ACTIONS
-- =============================================
DROP TABLE IF EXISTS `moderation_actions`;
CREATE TABLE `moderation_actions` (
  `action_id`   int(11)     NOT NULL AUTO_INCREMENT,
  `report_id`   int(11)     DEFAULT NULL,
  `admin_id`    int(11)     NOT NULL,
  `action_type` enum('warning','suspend','mark_viewed') NOT NULL,
  `action_note` text        DEFAULT NULL,
  `action_time` datetime    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`action_id`),
  KEY `ix_mod_actions_report` (`report_id`),
  KEY `ix_mod_actions_admin`  (`admin_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 15. RAG QUERIES  (query logging)
-- =============================================
DROP TABLE IF EXISTS `rag_queries`;
CREATE TABLE `rag_queries` (
  `query_id`           int(11)     NOT NULL AUTO_INCREMENT,
  `user_id`            int(11)     NOT NULL,
  `query_text`         text        NOT NULL,
  `course_code`        varchar(50) DEFAULT NULL,
  `chunks_retrieved`   int(11)     DEFAULT NULL,
  `response_generated` tinyint(1)  DEFAULT 0,
  `query_time`         timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`query_id`),
  KEY `ix_rag_queries_user`   (`user_id`),
  KEY `ix_rag_queries_course` (`course_code`),
  KEY `ix_rag_queries_time`   (`query_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 16. RESPONSE CACHE
-- =============================================
DROP TABLE IF EXISTS `response_cache`;
CREATE TABLE `response_cache` (
  `cache_key`  varchar(64)  NOT NULL,
  `cache_type` varchar(20)  NOT NULL,
  `cache_data` longtext     NOT NULL,
  `created_at` timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime     NOT NULL,
  `hit_count`  int(11)      DEFAULT 0,
  PRIMARY KEY (`cache_key`),
  KEY `ix_cache_type`       (`cache_type`),
  KEY `ix_cache_expires_at` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 17. SYSTEM SETTINGS
-- =============================================
DROP TABLE IF EXISTS `system_settings`;
CREATE TABLE `system_settings` (
  `setting_id`    int(11)      NOT NULL AUTO_INCREMENT,
  `setting_key`   varchar(100) NOT NULL,
  `setting_value` text         NOT NULL,
  `updated_by`    int(11)      DEFAULT NULL,
  `updated_at`    datetime     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`setting_id`),
  UNIQUE KEY `ix_system_settings_key` (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- FOREIGN KEY CONSTRAINTS
-- =============================================
ALTER TABLE `sessions`
  ADD CONSTRAINT `fk_sessions_user`         FOREIGN KEY (`user_id`)         REFERENCES `users`  (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_sessions_chat`         FOREIGN KEY (`current_chat_id`) REFERENCES `chats`  (`chat_id`) ON DELETE SET NULL;

ALTER TABLE `chats`
  ADD CONSTRAINT `fk_chats_user`            FOREIGN KEY (`user_id`)         REFERENCES `users`    (`user_id`)    ON DELETE CASCADE,
  ADD CONSTRAINT `fk_chats_session`         FOREIGN KEY (`session_id`)      REFERENCES `sessions` (`session_id`) ON DELETE SET NULL;

ALTER TABLE `messages`
  ADD CONSTRAINT `fk_messages_chat`         FOREIGN KEY (`chat_id`)         REFERENCES `chats`  (`chat_id`) ON DELETE CASCADE;

ALTER TABLE `token_limits`
  ADD CONSTRAINT `fk_token_limits_user`     FOREIGN KEY (`user_id`)         REFERENCES `users`  (`user_id`) ON DELETE CASCADE;

ALTER TABLE `course_materials`
  ADD CONSTRAINT `fk_materials_user`        FOREIGN KEY (`uploaded_by`)     REFERENCES `users`  (`user_id`) ON DELETE SET NULL;

ALTER TABLE `courses`
  ADD CONSTRAINT `fk_courses_instructor`    FOREIGN KEY (`instructor_id`)   REFERENCES `users`  (`user_id`) ON DELETE SET NULL;

ALTER TABLE `document_chunks`
  ADD CONSTRAINT `fk_chunks_material`       FOREIGN KEY (`material_id`)     REFERENCES `course_materials` (`material_id`) ON DELETE CASCADE;

ALTER TABLE `uploaded_files`
  ADD CONSTRAINT `fk_uploaded_files_user`   FOREIGN KEY (`user_id`)         REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_uploaded_files_chat`   FOREIGN KEY (`chat_id`)         REFERENCES `chats` (`chat_id`) ON DELETE SET NULL;

ALTER TABLE `password_reset_tokens`
  ADD CONSTRAINT `fk_reset_tokens_user`     FOREIGN KEY (`user_id`)         REFERENCES `users` (`user_id`) ON DELETE CASCADE;

ALTER TABLE `moderation_reports`
  ADD CONSTRAINT `fk_mod_reports_message`   FOREIGN KEY (`message_id`)      REFERENCES `messages` (`message_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_mod_reports_reporter`  FOREIGN KEY (`reported_by`)     REFERENCES `users`    (`user_id`)    ON DELETE CASCADE;

ALTER TABLE `moderation_actions`
  ADD CONSTRAINT `fk_mod_actions_report`    FOREIGN KEY (`report_id`)       REFERENCES `moderation_reports` (`report_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_mod_actions_admin`     FOREIGN KEY (`admin_id`)        REFERENCES `users` (`user_id`) ON DELETE CASCADE;

ALTER TABLE `rag_queries`
  ADD CONSTRAINT `fk_rag_queries_user`      FOREIGN KEY (`user_id`)         REFERENCES `users` (`user_id`) ON DELETE CASCADE;

ALTER TABLE `audit_logs`
  ADD CONSTRAINT `fk_audit_logs_admin`      FOREIGN KEY (`admin_id`)        REFERENCES `users` (`user_id`) ON DELETE SET NULL;

ALTER TABLE `system_settings`
  ADD CONSTRAINT `fk_settings_user`         FOREIGN KEY (`updated_by`)      REFERENCES `users` (`user_id`) ON DELETE SET NULL;

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================
-- TRIGGERS
-- =============================================

DROP TRIGGER IF EXISTS `update_chat_activity`;
DROP TRIGGER IF EXISTS `update_token_usage`;
DROP TRIGGER IF EXISTS `update_session_activity`;
DROP TRIGGER IF EXISTS `log_user_actions`;
DROP TRIGGER IF EXISTS `cleanup_expired_cache`;

DELIMITER $$

-- Auto-update chat.updated_at when a message is added
CREATE TRIGGER `update_chat_activity`
  AFTER INSERT ON `messages`
  FOR EACH ROW
BEGIN
  UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE chat_id = NEW.chat_id;
END$$

-- Auto-track token consumption
CREATE TRIGGER `update_token_usage`
  AFTER INSERT ON `messages`
  FOR EACH ROW
BEGIN
  UPDATE token_limits tl
  JOIN chats c ON c.user_id = tl.user_id
  SET tl.used_tokens = tl.used_tokens + COALESCE(NEW.token_count, 0)
  WHERE c.chat_id = NEW.chat_id
    AND (tl.period_end IS NULL OR tl.period_end > CURRENT_TIMESTAMP);
END$$

-- Auto-update session.last_activity when messages are sent
CREATE TRIGGER `update_session_activity`
  AFTER INSERT ON `messages`
  FOR EACH ROW
BEGIN
  UPDATE sessions s
  JOIN chats c ON c.user_id = s.user_id
  SET s.last_activity = CURRENT_TIMESTAMP
  WHERE c.chat_id = NEW.chat_id
    AND s.status = 'active'
    AND s.logout_time IS NULL;
END$$

-- Auto-log chat creation to audit_logs
CREATE TRIGGER `log_user_actions`
  AFTER INSERT ON `chats`
  FOR EACH ROW
BEGIN
  INSERT INTO audit_logs (admin_id, action, target_id, target_table, details, timestamp)
  VALUES (NEW.user_id, 'Chat Created', NEW.chat_id, 'chats',
          CONCAT('User created new chat: ', COALESCE(NEW.title, 'Untitled')),
          CURRENT_TIMESTAMP);
END$$

-- Auto-clean expired cache before each insert
CREATE TRIGGER `cleanup_expired_cache`
  BEFORE INSERT ON `response_cache`
  FOR EACH ROW
BEGIN
  DELETE FROM response_cache WHERE expires_at < CURRENT_TIMESTAMP;
END$$

DELIMITER ;

-- =============================================
-- DEFAULT SYSTEM SETTINGS
-- =============================================
INSERT INTO `system_settings` (`setting_key`, `setting_value`) VALUES
  ('global_token_limit', '100000'),
  ('guest_token_limit',  '1000');

-- =============================================
-- SEED: Create Your Admin User
-- =============================================
-- No default admin is seeded for security reasons.
-- Create your admin account after setup via the registration API:
--
--   POST /register
--   { "username": "your_admin", "password": "your_password", "email": "admin@yourdomain.com" }
--
-- Then promote to ADMIN role:
--   UPDATE users SET role = 'ADMIN' WHERE username = 'your_admin';
--
-- Or use the admin panel once the backend is running.
-- =============================================
