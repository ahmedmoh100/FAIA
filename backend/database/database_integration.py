"""
Database Integration Module for FAIA Backend
Handles database operations for users, messages, files, moderation, and tokenization
"""

import os
import re
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Add admin backend to path for shared database config (config.py, models.py)
# This is a known cross-folder dependency — see Section 9 in GITHUB-AUDIT.md
admin_backend_path = Path(__file__).resolve().parent.parent.parent / "admin" / "backend"
if str(admin_backend_path) not in sys.path:
    sys.path.insert(0, str(admin_backend_path))

# Add configuration path for faia_config_manager (moderation config)
_config_path = Path(__file__).resolve().parent.parent / "configuration"
if str(_config_path) not in sys.path:
    sys.path.insert(0, str(_config_path))

try:
    from config import engine, SessionLocal
    from sqlalchemy import text
    logger.info("Database config imported from admin backend")
except ImportError as e:
    logger.error("FATAL: Cannot import database config from admin backend: %s", e)
    raise ImportError("Database configuration must be imported from admin backend. Check admin/backend/config.py") from e

class DatabaseManager:
    """Manages all database operations for the FAIA system"""
    
    def __init__(self):
        self.engine = engine
        self._mod_pattern_cache: dict = {}
        
    # get_db_session removed - unused function
    
    # ==================== USER MANAGEMENT ====================
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user information by username"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT user_id, username, email, role, status, created_at, last_login
                    FROM users WHERE username = :username
                """), {"username": username})
                row = result.fetchone()
                if row:
                    return {
                        "user_id": row[0],
                        "username": row[1],
                        "email": row[2],
                        "role": row[3],
                        "status": row[4],
                        "created_at": row[5],
                        "last_login": row[6]
                    }
                return None
        except Exception as e:
            logger.error("Error getting user by username: %s", e)
            return None
    
    def create_user(self, username: str, email: str, password_hash: str, password_salt: str, role: str = 'STUDENT') -> Optional[int]:
        """Create a new user and return user_id"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO users (username, email, password_hash, password_salt, role)
                    VALUES (:username, :email, :password_hash, :password_salt, :role)
                """), {
                    "username": username,
                    "email": email,
                    "password_hash": password_hash,
                    "password_salt": password_salt,
                    "role": role
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating user: %s", e)
            return None
    
    def get_user_status(self, user_id: int) -> Optional[str]:
        """Get user's current status (active/suspended)"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT status FROM users WHERE user_id = :user_id
                """), {"user_id": user_id})
                row = result.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error("Error getting user status: %s", e)
            return None
    
    def get_user_credentials(self, username: str) -> Optional[Dict]:
        """Get user credentials for authentication"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT user_id, username, password_hash, password_salt, role, status
                    FROM users WHERE username = :username
                """), {"username": username})
                row = result.fetchone()
                if row:
                    return {
                        "user_id": row[0],
                        "username": row[1],
                        "password_hash": row[2],
                        "password_salt": row[3],
                        "role": row[4],
                        "status": row[5]
                    }
                return None
        except Exception as e:
            logger.error("Error getting user credentials: %s", e)
            return None
    
    def update_last_login(self, user_id: int):
        """Update user's last login time"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE users SET last_login = NOW() WHERE user_id = :user_id
                """), {"user_id": user_id})
                conn.commit()
        except Exception as e:
            logger.error("Error updating last login: %s", e)
    
    def update_user_password(self, user_id: int, password_hash: str, password_salt: str) -> bool:
        """Update user's password"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE users 
                    SET password_hash = :password_hash, password_salt = :password_salt 
                    WHERE user_id = :user_id
                """), {
                    "user_id": user_id,
                    "password_hash": password_hash,
                    "password_salt": password_salt
                })
                conn.commit()
                logger.info("Password updated for user_id: %s", user_id)
                return True
        except Exception as e:
            logger.error("Error updating password: %s", e)
            return False
    
    def update_user_status(self, user_id: int, status: str) -> bool:
        """Update user's status (active/suspended)"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE users 
                    SET status = :status 
                    WHERE user_id = :user_id
                """), {
                    "user_id": user_id,
                    "status": status
                })
                conn.commit()
                logger.info("User {user_id} status updated to: %s", status)
                return True
        except Exception as e:
            logger.error("Error updating user status: %s", e)
            return False
    
    # Columns that callers are permitted to update via this method.
    # Using an allowlist prevents SQL injection through dict key injection.
    # password_hash and password_salt intentionally excluded — use update_user_password() instead
    _USER_UPDATABLE_COLUMNS = {"username", "email", "role", "status", "last_login"}

    def update_user(self, user_id: int, updates: Dict) -> bool:
        """Update user information. Only columns in _USER_UPDATABLE_COLUMNS are accepted."""
        try:
            with self.engine.connect() as conn:
                set_clauses = []
                params = {"user_id": user_id}

                for key, value in updates.items():
                    if key in self._USER_UPDATABLE_COLUMNS:
                        set_clauses.append(f"{key} = :{key}")
                        params[key] = value

                if not set_clauses:
                    return False

                query = f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = :user_id"
                conn.execute(text(query), params)
                conn.commit()
                logger.info("User %s updated: %s", user_id, list(updates.keys()))
                return True
        except Exception as e:
            logger.error("Error updating user %s: %s", user_id, e)
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user and all associated data."""
        try:
            with self.engine.connect() as conn:
                # Delete in FK-safe order
                conn.execute(text("DELETE FROM messages WHERE chat_id IN (SELECT chat_id FROM chats WHERE user_id = :user_id)"), {"user_id": user_id})
                conn.execute(text("DELETE FROM chats WHERE user_id = :user_id"), {"user_id": user_id})
                conn.execute(text("DELETE FROM sessions WHERE user_id = :user_id"), {"user_id": user_id})
                conn.execute(text("DELETE FROM token_limits WHERE user_id = :user_id"), {"user_id": user_id})
                conn.execute(text("DELETE FROM uploaded_files WHERE user_id = :user_id"), {"user_id": user_id})
                # audit_logs.admin_id uses ON DELETE SET NULL — audit history is preserved, no delete needed
                conn.execute(text("DELETE FROM users WHERE user_id = :user_id"), {"user_id": user_id})
                conn.commit()
                logger.info("User %s deleted", user_id)
                return True
        except Exception as e:
            logger.error("Error deleting user %s: %s", user_id, e)
            return False
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email address"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT user_id, username, email, role, status
                    FROM users WHERE email = :email
                """), {"email": email})
                row = result.fetchone()
                if row:
                    return {
                        "user_id": row[0],
                        "username": row[1],
                        "email": row[2],
                        "role": row[3],
                        "status": row[4]
                    }
                return None
        except Exception as e:
            logger.error("Error getting user by email: %s", e)
            return None
    
    def create_password_reset_token(self, user_id: int, token: str) -> bool:
        """Create a password reset token (expires in 1 hour)"""
        try:
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO password_reset_tokens (user_id, token, expires_at)
                    VALUES (:user_id, :token, DATE_ADD(NOW(), INTERVAL 1 HOUR))
                """), {
                    "user_id": user_id,
                    "token": token
                })
                logger.info("Reset token created for user_id: %s", user_id)
                return True
        except Exception as e:
            logger.error("Error creating reset token: %s", e)
            return False
    
    def validate_reset_token(self, token: str) -> Optional[Dict]:
        """Validate a password reset token. Returns user_id if valid, None otherwise."""
        try:
            with self.engine.connect() as conn:
                # Expiry check done in SQL using server time to avoid client/server timezone mismatch
                result = conn.execute(text("""
                    SELECT user_id, used
                    FROM password_reset_tokens
                    WHERE token = :token
                      AND expires_at > NOW()
                """), {"token": token})
                row = result.fetchone()

                if not row:
                    logger.warning("Reset token not found or expired")
                    return None

                user_id, used = row

                if used:
                    logger.warning("Reset token already used")
                    return None

                return {"user_id": user_id}
        except Exception as e:
            logger.error("Error validating reset token: %s", e)
            return None
    
    def mark_reset_token_used(self, token: str) -> bool:
        """Mark reset token as used"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE password_reset_tokens
                    SET used = TRUE
                    WHERE token = :token
                """), {"token": token})
                conn.commit()
                return True
        except Exception as e:
            logger.error("Error marking token as used: %s", e)
            return False
    
    # ==================== SESSION MANAGEMENT ====================
    
    def create_session(self, user_id: int, ip_address: str = None) -> Optional[int]:
        """Create a new session and return the session_id."""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO sessions (user_id, ip_address, status, login_time, last_activity)
                    VALUES (:user_id, :ip_address, 'active', NOW(), NOW())
                """), {"user_id": user_id, "ip_address": ip_address})
                session_id = result.lastrowid
                logger.info("Session created: id=%s user_id=%s", session_id, user_id)
                return session_id
        except Exception as e:
            logger.error("Error creating session: %s", e)
            return None
    
    def end_session(self, session_id: int):
        """End a session"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE sessions 
                    SET logout_time = NOW(), status = 'ended' 
                    WHERE session_id = :session_id
                """), {"session_id": session_id})
                conn.commit()
        except Exception as e:
            logger.error("Error ending session: %s", e)
    
    def update_session_activity(self, session_id: int):
        """Update session last activity time"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE sessions 
                    SET last_activity = NOW() 
                    WHERE session_id = :session_id
                """), {"session_id": session_id})
                conn.commit()
        except Exception as e:
            logger.error("Error updating session activity: %s", e)
    
    def update_session_chat(self, session_id: int, chat_id: int):
        """Update session's current chat_id"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE sessions 
                    SET current_chat_id = :chat_id,
                        last_activity = NOW()
                    WHERE session_id = :session_id
                """), {"session_id": session_id, "chat_id": chat_id})
                conn.commit()
                logger.info("Updated session {session_id} with chat_id %s", chat_id)
        except Exception as e:
            logger.error("Error updating session chat: %s", e)
    
    def is_session_valid(self, session_id: int, user_id: int) -> bool:
        """Check if a session is still valid and active"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT session_id 
                    FROM sessions 
                    WHERE session_id = :session_id 
                    AND user_id = :user_id
                    AND status = 'active'
                    AND logout_time IS NULL
                    AND (
                        last_activity IS NULL 
                        OR last_activity > DATE_SUB(NOW(), INTERVAL 30 MINUTE)
                    )
                """), {"session_id": session_id, "user_id": user_id})
                
                is_valid = result.fetchone() is not None
                logger.info("Session validation query result for session {session_id}: %s", is_valid)
                return is_valid
        except Exception as e:
            logger.error("Error validating session: %s", e)
            return False
    
    def get_user_active_session(self, user_id: int) -> Optional[Dict]:
        """Get user's most recent active session"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT session_id, user_id, login_time, last_activity, ip_address, status
                    FROM sessions 
                    WHERE user_id = :user_id
                    AND status = 'active'
                    AND logout_time IS NULL
                    ORDER BY last_activity DESC
                    LIMIT 1
                """), {"user_id": user_id})
                
                row = result.fetchone()
                if row:
                    return {
                        "session_id": row[0],
                        "user_id": row[1],
                        "login_time": row[2],
                        "last_activity": row[3],
                        "ip_address": row[4],
                        "status": row[5]
                    }
                return None
        except Exception as e:
            logger.error("Error getting user active session: %s", e)
            return None
    
    def get_session(self, session_id: int) -> Optional[Dict]:
        """Get a single session by ID"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT session_id, user_id, login_time, logout_time, ip_address, 
                           status, last_activity, current_chat_id
                    FROM sessions
                    WHERE session_id = :session_id
                """), {"session_id": session_id})
                row = result.fetchone()
                if row:
                    return {
                        "session_id": row[0],
                        "user_id": row[1],
                        "login_time": row[2],
                        "logout_time": row[3],
                        "ip_address": row[4],
                        "status": row[5],
                        "last_activity": row[6],
                        "current_chat_id": row[7]
                    }
                return None
        except Exception as e:
            logger.error("Error getting session: %s", e)
            return None
    
    def get_active_sessions(self) -> List[Dict]:
        """Get all active sessions"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT s.session_id, s.user_id, u.username, u.email, u.role,
                           s.login_time, s.last_activity, s.ip_address,
                           TIMESTAMPDIFF(MINUTE, s.login_time, NOW()) as duration_minutes
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.logout_time IS NULL 
                    AND s.status = 'active'
                    AND s.last_activity > DATE_SUB(NOW(), INTERVAL 30 MINUTE)
                    ORDER BY s.last_activity DESC
                """))
                
                sessions = []
                for row in result:
                    sessions.append({
                        "session_id": row[0],
                        "user_id": row[1],
                        "username": row[2],
                        "email": row[3],
                        "role": row[4],
                        "login_time": row[5],
                        "last_activity": row[6],
                        "ip_address": row[7],
                        "duration_minutes": row[8]
                    })
                return sessions
        except Exception as e:
            logger.error("Error getting active sessions: %s", e)
            return []
    
    def get_all_sessions(self, limit: int = 100) -> List[Dict]:
        """Get all sessions (active and ended)"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT s.session_id, s.user_id, u.username, u.email, u.role,
                           s.login_time, s.logout_time, s.last_activity, s.ip_address, s.status,
                           CASE 
                               WHEN s.logout_time IS NOT NULL 
                               THEN TIMESTAMPDIFF(MINUTE, s.login_time, s.logout_time)
                               ELSE TIMESTAMPDIFF(MINUTE, s.login_time, NOW())
                           END as duration_minutes
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    ORDER BY s.login_time DESC
                    LIMIT :limit
                """), {"limit": limit})
                
                sessions = []
                for row in result:
                    sessions.append({
                        "session_id": row[0],
                        "user_id": row[1],
                        "username": row[2],
                        "email": row[3],
                        "role": row[4],
                        "login_time": row[5],
                        "logout_time": row[6],
                        "last_activity": row[7],
                        "ip_address": row[8],
                        "status": row[9],
                        "duration_minutes": row[10]
                    })
                return sessions
        except Exception as e:
            logger.error("Error getting all sessions: %s", e)
            return []
    
    def get_user_sessions(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get sessions for a specific user"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT session_id, login_time, logout_time, last_activity, 
                           ip_address, status,
                           CASE 
                               WHEN logout_time IS NOT NULL 
                               THEN TIMESTAMPDIFF(MINUTE, login_time, logout_time)
                               ELSE TIMESTAMPDIFF(MINUTE, login_time, NOW())
                           END as duration_minutes
                    FROM sessions
                    WHERE user_id = :user_id
                    ORDER BY login_time DESC
                    LIMIT :limit
                """), {"user_id": user_id, "limit": limit})
                
                sessions = []
                for row in result:
                    sessions.append({
                        "session_id": row[0],
                        "login_time": row[1],
                        "logout_time": row[2],
                        "last_activity": row[3],
                        "ip_address": row[4],
                        "status": row[5],
                        "duration_minutes": row[6]
                    })
                return sessions
        except Exception as e:
            logger.error("Error getting user sessions: %s", e)
            return []
    
    # ==================== CHAT AND MESSAGE MANAGEMENT ====================
    
    def create_chat(self, user_id: int, title: str = None) -> Optional[int]:
        """Create a new chat"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO chats (user_id, title)
                    VALUES (:user_id, :title)
                """), {"user_id": user_id, "title": title or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"})
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating chat: %s", e)
            return None
    
    def save_message(self, chat_id: int, sender: str, content: str, token_count: int = 0) -> Optional[int]:
        """Save a message to the database"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO messages (chat_id, sender, content, token_count)
                    VALUES (:chat_id, :sender, :content, :token_count)
                """), {
                    "chat_id": chat_id,
                    "sender": sender,
                    "content": content,
                    "token_count": token_count
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error saving message: %s", e)
            return None
    
    def get_chat_history(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get chat history for a user"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT c.chat_id, c.title, c.created_at, c.updated_at,
                           COUNT(m.message_id) as message_count
                    FROM chats c
                    LEFT JOIN messages m ON c.chat_id = m.chat_id
                    WHERE c.user_id = :user_id
                    GROUP BY c.chat_id, c.title, c.created_at, c.updated_at
                    ORDER BY c.updated_at DESC
                    LIMIT :limit
                """), {"user_id": user_id, "limit": limit})
                
                chats = []
                for row in result:
                    chats.append({
                        "chat_id": row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "message_count": row[4]
                    })
                return chats
        except Exception as e:
            logger.error("Error getting chat history: %s", e)
            return []
    
    def get_chat_messages(self, chat_id: int, limit: int = None) -> List[Dict]:
        """Get messages for a specific chat. limit=None returns all (for AI context), limit=N returns most recent N (for UI)."""
        try:
            with self.engine.connect() as conn:
                if limit:
                    result = conn.execute(text("""
                        SELECT message_id, sender, content, token_count, created_at
                        FROM messages
                        WHERE chat_id = :chat_id
                        ORDER BY created_at ASC
                        LIMIT :limit
                    """), {"chat_id": chat_id, "limit": limit})
                    rows = list(result)
                else:
                    result = conn.execute(text("""
                        SELECT message_id, sender, content, token_count, created_at
                        FROM messages
                        WHERE chat_id = :chat_id
                        ORDER BY created_at ASC
                    """), {"chat_id": chat_id})
                    rows = list(result)

                messages = []
                for row in rows:
                    created_at = row[4]
                    # Serialize datetime to ISO string so JS new Date() can parse it correctly
                    if hasattr(created_at, 'isoformat'):
                        created_at = created_at.isoformat()
                    messages.append({
                        "message_id": row[0],
                        "sender": row[1],
                        "content": row[2],
                        "token_count": row[3],
                        "created_at": created_at
                    })
                return messages
        except Exception as e:
            logger.error("Error getting chat messages: %s", e)
            return []
    
    def count_chat_messages(self, chat_id: int) -> int:
        """Return the number of messages in a chat (cheap COUNT query)."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM messages WHERE chat_id = :chat_id
                """), {"chat_id": chat_id})
                return result.fetchone()[0]
        except Exception as e:
            logger.error("Error counting messages for chat {chat_id}: %s", e)
            return 0

    def delete_old_messages(self, chat_id: int, keep_count: int) -> int:
        """Delete oldest messages in a chat, keeping only the most recent keep_count. Returns number deleted."""
        try:
            with self.engine.connect() as conn:
                # Get IDs of messages to keep (most recent keep_count)
                result = conn.execute(text("""
                    SELECT message_id FROM messages
                    WHERE chat_id = :chat_id
                    ORDER BY created_at DESC
                    LIMIT :keep_count
                """), {"chat_id": chat_id, "keep_count": keep_count})
                keep_ids = [row[0] for row in result]

                if not keep_ids:
                    return 0

                # Delete everything not in the keep list
                placeholders = ','.join([str(i) for i in keep_ids])
                sql = """
                    DELETE FROM messages
                    WHERE chat_id = :chat_id
                    AND message_id NOT IN ({})
                """.format(placeholders)
                result = conn.execute(text(sql), {"chat_id": chat_id})
                conn.commit()
                deleted = result.rowcount
                return deleted
        except Exception as e:
            logger.error("Error deleting old messages for chat {chat_id}: %s", e)
            return 0

    def get_user_chats(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get all chats for a user"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT chat_id, user_id, title, created_at
                    FROM chats
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """), {"user_id": user_id, "limit": limit})
                
                chats = []
                for row in result:
                    chats.append({
                        "chat_id": row[0],
                        "user_id": row[1],
                        "title": row[2],
                        "created_at": row[3]
                    })
                return chats
        except Exception as e:
            logger.error("Error getting user chats: %s", e)
            return []
    
    def update_chat_title(self, chat_id: int, title: str) -> bool:
        """Update chat title"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE chats SET title = :title WHERE chat_id = :chat_id
                """), {"chat_id": chat_id, "title": title})
                conn.commit()
                return True
        except Exception as e:
            logger.error("Error updating chat title: %s", e)
            return False
    
    def delete_chat_messages(self, chat_id: int) -> bool:
        """Delete all messages in a chat"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM messages WHERE chat_id = :chat_id"), {"chat_id": chat_id})
                conn.commit()
                return True
        except Exception as e:
            logger.error("Error deleting chat messages: %s", e)
            return False
    
    def get_chat_by_id(self, chat_id: int) -> Optional[Dict]:
        """Get a specific chat by ID"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT chat_id, user_id, title, created_at, updated_at
                    FROM chats
                    WHERE chat_id = :chat_id
                """), {"chat_id": chat_id})
                
                row = result.fetchone()
                if row:
                    return {
                        "chat_id": row[0],
                        "user_id": row[1],
                        "title": row[2],
                        "created_at": row[3],
                        "updated_at": row[4]
                    }
                return None
        except Exception as e:
            logger.error("Error getting chat by ID: %s", e)
            return None
    
    def delete_chat(self, chat_id: int) -> bool:
        """Delete a chat and all its messages"""
        try:
            with self.engine.connect() as conn:
                # Delete messages first (foreign key constraint)
                conn.execute(text("""
                    DELETE FROM messages WHERE chat_id = :chat_id
                """), {"chat_id": chat_id})
                
                # Delete the chat
                conn.execute(text("""
                    DELETE FROM chats WHERE chat_id = :chat_id
                """), {"chat_id": chat_id})
                
                conn.commit()
                return True
        except Exception as e:
            logger.error("Error deleting chat: %s", e)
            return False
    
    def return_tokens(self, user_id: int, tokens: int) -> bool:
        """Return tokens to user (subtract from used_tokens)"""
        try:
            with self.engine.connect() as conn:
                # Subtract from used_tokens (can't go below 0)
                conn.execute(text("""
                    UPDATE token_limits
                    SET used_tokens = GREATEST(0, used_tokens - :tokens)
                    WHERE user_id = :user_id
                """), {"user_id": user_id, "tokens": tokens})
                
                conn.commit()
                return True
        except Exception as e:
            logger.error("Error returning tokens: %s", e)
            return False
    
    # ==================== FILE MANAGEMENT ====================
    
    def save_uploaded_file(self, user_id: int, chat_id: int, file_name: str, 
                          file_path: str, file_type: str) -> Optional[int]:
        """Save uploaded file information to database"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO uploaded_files (user_id, chat_id, file_name, file_path, file_type)
                    VALUES (:user_id, :chat_id, :file_name, :file_path, :file_type)
                """), {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_type": file_type
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error saving uploaded file: %s", e)
            return None
    
    def get_user_files(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get files uploaded by a user"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT file_id, file_name, file_type, upload_time, status
                    FROM uploaded_files
                    WHERE user_id = :user_id
                    ORDER BY upload_time DESC
                    LIMIT :limit
                """), {"user_id": user_id, "limit": limit})
                
                files = []
                for row in result:
                    files.append({
                        "file_id": row[0],
                        "file_name": row[1],
                        "file_type": row[2],
                        "upload_time": row[3],
                        "status": row[4]
                    })
                return files
        except Exception as e:
            logger.error("Error getting user files: %s", e)
            return []
    
    def delete_file(self, file_id: int) -> bool:
        """Delete a file record from database"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM uploaded_files WHERE file_id = :file_id"), {"file_id": file_id})
                conn.commit()
                return True
        except Exception as e:
            logger.error("Error deleting file: %s", e)
            return False
    
    # ==================== MODERATION SYSTEM ====================
    
    def _get_mod_pattern(self, keyword: str):
        """Return a compiled regex for the keyword, using cache to avoid recompilation."""
        if keyword not in self._mod_pattern_cache:
            self._mod_pattern_cache[keyword] = re.compile(r'\b' + re.escape(keyword.lower()) + r'\b')
        return self._mod_pattern_cache[keyword]

    def check_content_moderation(self, content: str) -> Dict[str, Any]:
        """Check content against moderation keyword lists. Uses word-boundary matching to avoid false positives."""
        try:
            from faia_config_manager import get_moderation_config
            mod_config = get_moderation_config()
            if not mod_config.get("enabled", True):
                return {"flagged": False, "risk_level": "low", "flags": [], "reason": None, "category": None}
            risk_levels = mod_config.get("risk_levels", {})
            categories = mod_config.get("categories", {})
        except Exception as e:
            logger.warning("Could not load moderation config, using fallback: %s", e)
            risk_levels = {
                "high": {"keywords": ["kill", "murder", "suicide", "bomb", "weapon", "violence", "attack"]},
                "medium": {"keywords": ["hate", "racist", "discrimination", "harassment", "abuse"]},
                "low": {"keywords": ["spam", "advertisement"]},
            }
            categories = {"violence": ["kill", "murder", "weapon"], "hate_speech": ["hate", "racist"]}

        flags = []
        risk_level = "low"
        detected_category = "other"
        content_lower = content.lower()

        for level_name in ["high", "medium", "low"]:
            for keyword in risk_levels.get(level_name, {}).get("keywords", []):
                # Word-boundary match — prevents 'kill' matching inside 'skill'
                if self._get_mod_pattern(keyword).search(content_lower):
                    flags.append(keyword)
                    if level_name == "high":
                        risk_level = "high"
                    elif level_name == "medium" and risk_level != "high":
                        risk_level = "medium"

        for cat_name, cat_keywords in categories.items():
            for keyword in cat_keywords:
                if self._get_mod_pattern(keyword).search(content_lower):
                    detected_category = cat_name
                    break
            if detected_category != "other":
                break

        unique_flags = list(set(flags))
        return {
            "flagged": bool(unique_flags),
            "risk_level": risk_level,
            "flags": unique_flags,
            "category": detected_category,
            "reason": f"Content flagged for {detected_category}: {', '.join(unique_flags)}" if unique_flags else None,
        }
    
    def create_moderation_report(self, report_data: Dict) -> Optional[int]:
        """Create a general moderation report"""
        try:
            with self.engine.begin() as conn:
                # Insert into a general moderation_flags table
                result = conn.execute(text("""
                    INSERT INTO moderation_flags 
                    (target_type, target_id, reason, content_preview, reporter_name, reporter_id, 
                     status, priority, category, created_at, updated_at)
                    VALUES (:target_type, :target_id, :reason, :content_preview, :reporter_name, 
                            :reporter_id, :status, :priority, :category, NOW(), NOW())
                """), {
                    "target_type": report_data.get("target_type"),
                    "target_id": report_data.get("target_id"),
                    "reason": report_data.get("reason"),
                    "content_preview": report_data.get("content_preview"),
                    "reporter_name": report_data.get("reporter_name"),
                    "reporter_id": report_data.get("reporter_id"),
                    "status": report_data.get("status", "new"),
                    "priority": report_data.get("priority", "medium"),
                    "category": report_data.get("category", "General")
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating moderation report: %s", e)
            return None
    
    def create_message_moderation_report(self, message_id: int, reported_by: int, 
                               reason: str, auto_flagged: bool = False) -> Optional[int]:
        """Create a moderation report for messages (legacy method)"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO moderation_reports (message_id, reported_by, reason, status)
                    VALUES (:message_id, :reported_by, :reason, :status)
                """), {
                    "message_id": message_id,
                    "reported_by": reported_by,
                    "reason": reason,
                    "status": "pending"
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating moderation report: %s", e)
            return None
    
    def get_pending_moderation_reports(self, limit: int = 50) -> List[Dict]:
        """Get pending moderation reports"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT mr.report_id, mr.message_id, mr.reason, mr.created_at,
                           m.content, u.username
                    FROM moderation_reports mr
                    JOIN messages m ON mr.message_id = m.message_id
                    JOIN chats c ON m.chat_id = c.chat_id
                    JOIN users u ON c.user_id = u.user_id
                    WHERE mr.status = 'pending'
                    ORDER BY mr.created_at DESC
                    LIMIT :limit
                """), {"limit": limit})
                
                reports = []
                for row in result:
                    reports.append({
                        "report_id": row[0],
                        "message_id": row[1],
                        "reason": row[2],
                        "created_at": row[3],
                        "content": row[4],
                        "username": row[5]
                    })
                return reports
        except Exception as e:
            logger.error("Error getting moderation reports: %s", e)
            return []
    
    # ==================== TOKEN MANAGEMENT ====================
    
    def get_user_token_limit(self, user_id: int) -> Dict[str, Any]:
        """Get user's token limit and usage. Creates a default limit row if none exists."""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    SELECT max_tokens, used_tokens, period_start, period_end
                    FROM token_limits
                    WHERE user_id = :user_id
                    ORDER BY period_start DESC
                    LIMIT 1
                """), {"user_id": user_id})

                row = result.fetchone()
                if row:
                    max_tokens = row[0] or self.get_global_token_limit()
                    used_tokens = row[1] or 0
                    return {
                        "max_tokens": max_tokens,
                        "used_tokens": used_tokens,
                        "remaining_tokens": max_tokens - used_tokens,
                        "period_start": row[2],
                        "period_end": row[3],
                        "usage_percentage": (used_tokens / max_tokens) * 100 if max_tokens > 0 else 0
                    }

                # No row — create with zero usage in the same transaction
                global_limit = self.get_global_token_limit()
                conn.execute(text("""
                    INSERT INTO token_limits (user_id, max_tokens, used_tokens, period_start, period_end)
                    VALUES (:user_id, :max_tokens, 0, NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY))
                """), {"user_id": user_id, "max_tokens": global_limit})

                return {
                    "max_tokens": global_limit,
                    "used_tokens": 0,
                    "remaining_tokens": global_limit,
                    "period_start": datetime.now(),
                    "period_end": datetime.now() + timedelta(days=30),
                    "usage_percentage": 0
                }
        except Exception as e:
            logger.error("Error getting token limit for user %s: %s", user_id, e)
            global_limit = self.get_global_token_limit()
            return {"max_tokens": global_limit, "used_tokens": 0, "remaining_tokens": global_limit, "usage_percentage": 0}
    
    def create_token_limit(self, user_id: int, max_tokens: int = None) -> Optional[int]:
        """Create token limit for a user"""
        try:
            # Use global token limit if not specified
            if max_tokens is None:
                max_tokens = self.get_global_token_limit()
                
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO token_limits (user_id, max_tokens, period_start, period_end)
                    VALUES (:user_id, :max_tokens, NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY))
                """), {"user_id": user_id, "max_tokens": max_tokens})
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating token limit: %s", e)
            return None
    
    def update_token_usage(self, user_id: int, tokens_used: int) -> bool:
        """Update user's token usage (upsert: update existing row or create with initial usage)"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    UPDATE token_limits SET used_tokens = COALESCE(used_tokens, 0) + :tokens_used
                    WHERE user_id = :user_id
                    ORDER BY period_start DESC
                    LIMIT 1
                """), {"tokens_used": tokens_used, "user_id": user_id})

                if result.rowcount == 0:
                    # No existing row — create with initial usage
                    conn.execute(text("""
                        INSERT INTO token_limits (user_id, max_tokens, used_tokens, period_start, period_end)
                        VALUES (:user_id, :max_tokens, :tokens_used, NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY))
                    """), {"user_id": user_id, "max_tokens": self.get_global_token_limit(), "tokens_used": tokens_used})

            return True
        except Exception as e:
            logger.error("Error updating token usage: %s", e)
            return False
    
    def check_token_limit(self, user_id: int, requested_tokens: int) -> Dict[str, Any]:
        """Check if user can use requested tokens"""
        token_info = self.get_user_token_limit(user_id)
        
        can_use = token_info["remaining_tokens"] >= requested_tokens
        
        return {
            "can_use": can_use,
            "remaining_tokens": token_info["remaining_tokens"],
            "requested_tokens": requested_tokens,
            "usage_percentage": token_info["usage_percentage"],
            "message": "Token limit exceeded" if not can_use else "Tokens available"
        }
    
    def reset_user_tokens(self, user_id: int) -> bool:
        """Reset user's token usage to 0"""
        try:
            with self.engine.connect() as conn:
                # Reset used_tokens to 0 and update period_start to now
                conn.execute(text("""
                    UPDATE token_limits 
                    SET used_tokens = 0,
                        period_start = NOW(),
                        period_end = DATE_ADD(NOW(), INTERVAL 30 DAY)
                    WHERE user_id = :user_id
                """), {"user_id": user_id})
                conn.commit()
                
                logger.info("Reset token usage for user_id %s", user_id)
                return True
        except Exception as e:
            logger.error("Error resetting tokens for user {user_id}: %s", e)
            return False
    
    def update_all_user_token_limits(self, new_max_tokens: int) -> bool:
        """Update all users' token limits to new global limit"""
        try:
            with self.engine.connect() as conn:
                # Update all existing token limits to new maximum
                result = conn.execute(text("""
                    UPDATE token_limits 
                    SET max_tokens = :new_max_tokens
                    WHERE max_tokens != :new_max_tokens
                """), {"new_max_tokens": new_max_tokens})
                
                conn.commit()
                rows_affected = result.rowcount
                logger.info("Updated token limits for {rows_affected} users to %s", new_max_tokens)
                return True
        except Exception as e:
            logger.error("Error updating all user token limits: %s", e)
            return False
    
    # ==================== AUDIT LOGGING ====================
    
    def log_audit_action(self, admin_id: int, action: str, target_id: int = None, 
                        target_table: str = None) -> Optional[int]:
        """Log an audit action"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO audit_logs (admin_id, action, target_id, target_table)
                    VALUES (:admin_id, :action, :target_id, :target_table)
                """), {
                    "admin_id": admin_id,
                    "action": action,
                    "target_id": target_id,
                    "target_table": target_table
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error logging audit action: %s", e)
            return None
    
    def get_audit_logs(self, limit: int = 100, user_id: int = None) -> List[Dict]:
        """Get audit logs"""
        try:
            with self.engine.connect() as conn:
                query = """
                    SELECT a.log_id, a.admin_id, u.username, a.action, 
                           a.target_id, a.target_table, a.timestamp
                    FROM audit_logs a
                    LEFT JOIN users u ON a.admin_id = u.user_id
                """
                params = {"limit": limit}
                
                if user_id:
                    query += " WHERE a.admin_id = :user_id"
                    params["user_id"] = user_id
                
                query += " ORDER BY a.timestamp DESC LIMIT :limit"
                
                result = conn.execute(text(query), params)
                logs = []
                for row in result:
                    logs.append({
                        "log_id": row[0],
                        "admin_id": row[1],
                        "username": row[2],
                        "action": row[3],
                        "target_id": row[4],
                        "target_table": row[5],
                        "timestamp": row[6]
                    })
                return logs
        except Exception as e:
            logger.error("Error getting audit logs: %s", e)
            return []
    
    # ==================== SYSTEM MONITORING ====================
    # log_system_stats removed - unused function
    
    def get_moderation_flag(self, flag_id: int) -> Optional[Dict]:
        """Get a single moderation flag by ID"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT id, target_type, target_id, reason, content_preview, 
                           reporter_name, reporter_id, status, priority, category,
                           UNIX_TIMESTAMP(created_at) as created_at,
                           UNIX_TIMESTAMP(updated_at) as updated_at
                    FROM moderation_flags
                    WHERE id = :flag_id
                """), {"flag_id": flag_id})
                
                row = result.fetchone()
                if row:
                    # Get user_id from target_id if target_type is 'user' or 'message'
                    user_id = None
                    if row[1] == 'user':
                        user_id = row[2]
                    elif row[1] == 'message':
                        # Get user_id from message
                        msg_result = conn.execute(text("""
                            SELECT c.user_id 
                            FROM messages m 
                            JOIN chats c ON m.chat_id = c.chat_id 
                            WHERE m.message_id = :message_id
                        """), {"message_id": row[2]})
                        msg_row = msg_result.fetchone()
                        if msg_row:
                            user_id = msg_row[0]
                    
                    return {
                        "id": row[0],
                        "target_type": row[1],
                        "target_id": row[2],
                        "reason": row[3],
                        "content_preview": row[4],
                        "reporter_name": row[5],
                        "reporter_id": row[6],
                        "status": row[7],
                        "priority": row[8],
                        "category": row[9],
                        "created_at": row[10],
                        "updated_at": row[11],
                        "user_id": user_id
                    }
                return None
        except Exception as e:
            logger.error("Error getting moderation flag: %s", e)
            return None
    
    def get_moderation_flags(self, status: str = None) -> List[Dict]:
        """Get moderation flags/reports"""
        try:
            with self.engine.connect() as conn:
                query = """
                    SELECT id, target_type, target_id, reason, content_preview, 
                           reporter_name, reporter_id, status, priority, category,
                           UNIX_TIMESTAMP(created_at) as created_at,
                           UNIX_TIMESTAMP(updated_at) as updated_at
                    FROM moderation_flags
                """
                params = {}
                
                if status:
                    query += " WHERE status = :status"
                    params["status"] = status
                
                query += " ORDER BY created_at DESC"
                
                result = conn.execute(text(query), params)
                flags = []
                for row in result:
                    flags.append({
                        "id": row[0],
                        "target_type": row[1],
                        "target_id": row[2],
                        "reason": row[3],
                        "content_preview": row[4],
                        "reporter_name": row[5],
                        "reporter_id": row[6],
                        "status": row[7],
                        "priority": row[8],
                        "category": row[9],
                        "created_at": row[10],
                        "updated_at": row[11]
                    })
                return flags
        except Exception as e:
            logger.error("Error getting moderation flags: %s", e)
            return []
    
    def update_moderation_flag(self, flag_id: int, status: str, admin_notes: str = None) -> bool:
        """Update moderation flag status"""
        try:
            with self.engine.connect() as conn:
                query = """
                    UPDATE moderation_flags 
                    SET status = :status, updated_at = NOW()
                """
                params = {
                    "flag_id": flag_id,
                    "status": status
                }
                
                if admin_notes:
                    query += ", admin_notes = :admin_notes"
                    params["admin_notes"] = admin_notes
                
                query += " WHERE id = :flag_id"
                
                result = conn.execute(text(query), params)
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error("Error updating moderation flag: %s", e)
            return False
    
    def take_moderation_action(self, flag_id: int, action: str, admin_id: int, notes: str = None) -> bool:
        """Take moderation action on a flag and update user status if needed"""
        try:
            with self.engine.connect() as conn:
                # Get flag details
                flag_result = conn.execute(text("""
                    SELECT target_type, target_id, reporter_id FROM moderation_flags
                    WHERE id = :flag_id
                """), {"flag_id": flag_id})
                flag_row = flag_result.fetchone()
                
                if not flag_row:
                    logger.error("Flag %s not found", flag_id)
                    return False
                
                target_type, target_id, reporter_id = flag_row
                
                # Map actions to statuses
                action_to_status = {
                    "validate": "validated",
                    "warn": "warned",
                    "suspend": "suspended",
                    "mark_viewed": "dismissed",
                    "dismiss": "dismissed",
                    "mark_reviewed": "validated",  # For AI flags - mark as reviewed/validated
                    "resolve": "resolved"
                }
                
                new_status = action_to_status.get(action, "validated")
                
                # Update flag status
                conn.execute(text("""
                    UPDATE moderation_flags
                    SET status = :status, updated_at = NOW(), admin_notes = :admin_notes
                    WHERE id = :flag_id
                """), {
                    "flag_id": flag_id,
                    "status": new_status,
                    "admin_notes": notes or f"Action taken: {action}"
                })
                
                # Create moderation action record
                if target_type == "message" and target_id and not target_id.startswith("pending_"):
                    try:
                        # Get message_id and find user
                        msg_result = conn.execute(text("""
                            SELECT c.user_id FROM messages m
                            JOIN chats c ON m.chat_id = c.chat_id
                            WHERE m.message_id = :message_id
                        """), {"message_id": int(target_id)})
                        msg_row = msg_result.fetchone()
                        
                        if msg_row:
                            user_id = msg_row[0]
                            
                            # Create action record in moderation_actions (if using legacy table)
                            try:
                                conn.execute(text("""
                                    INSERT INTO moderation_actions 
                                    (report_id, admin_id, action_type, action_note)
                                    VALUES (NULL, :admin_id, :action_type, :action_note)
                                """), {
                                    "admin_id": admin_id,
                                    "action_type": action if action in ['warning', 'suspend', 'mark_viewed'] else 'mark_viewed',
                                    "action_note": notes or f"Moderation action: {action} on flag {flag_id}"
                                })
                            except Exception as e:
                                logger.debug("moderation_actions insert skipped: %s", e)
                            
                            # Handle user suspension
                            if action == "suspend":
                                conn.execute(text("""
                                    UPDATE users SET status = 'SUSPENDED' WHERE user_id = :user_id
                                """), {"user_id": user_id})
                                logger.info("User {user_id} suspended due to flag %s", flag_id)
                                
                                # End active sessions
                                conn.execute(text("""
                                    UPDATE sessions SET status = 'ended', logout_time = NOW()
                                    WHERE user_id = :user_id AND status = 'active'
                                """), {"user_id": user_id})
                    except Exception as e:
                        logger.warning("Could not process user action for flag {flag_id}: %s", e)
                
                conn.commit()
                logger.info("Moderation action '{action}' taken on flag {flag_id} by admin %s", admin_id)
                return True
                
        except Exception as e:
            logger.error("Error taking moderation action: %s", e)
            return False
    
    def link_report_to_message(self, temp_target_id: str, actual_message_id: int) -> bool:
        """Link a moderation report from temporary ID to actual message ID"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    UPDATE moderation_flags
                    SET target_id = :actual_id
                    WHERE target_id = :temp_id AND target_type = 'message'
                """), {
                    "actual_id": str(actual_message_id),
                    "temp_id": temp_target_id
                })
                conn.commit()
                if result.rowcount > 0:
                    logger.info("Linked report from {temp_target_id} to message %s", actual_message_id)
                return result.rowcount > 0
        except Exception as e:
            logger.error("Error linking report to message: %s", e)
            return False
    
    def check_user_report_rate_limit(self, user_id: int) -> Dict[str, Any]:
        """Check if user has exceeded report rate limits"""
        try:
            with self.engine.connect() as conn:
                # Count reports in last hour
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM moderation_flags
                    WHERE reporter_id = :user_id
                    AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
                """), {"user_id": str(user_id)})
                
                count = result.scalar() or 0
                
                # Get limit from config (default 5)
                max_reports = 5
                try:
                    from pathlib import Path
                    import sys
                    config_path = Path(__file__).parent.parent / "configuration"
                    if str(config_path) not in sys.path:
                        sys.path.insert(0, str(config_path))
                    from faia_config_manager import get_moderation_config
                    mod_config = get_moderation_config()
                    max_reports = mod_config.get("rate_limiting", {}).get("max_reports_per_user_per_hour", 5)
                except Exception as e:
                    logger.debug("Could not load moderation rate limit config, using default: %s", e)
                
                return {
                    "allowed": count < max_reports,
                    "current_count": count,
                    "max_allowed": max_reports,
                    "reset_in_seconds": 3600
                }
        except Exception as e:
            logger.error("Error checking report rate limit: %s", e)
            return {"allowed": True, "current_count": 0, "max_allowed": 5}
    
    # ==================== RAG SYSTEM METHODS ====================
    
    def create_course_material(self, filename: str, original_filename: str, file_path: str, 
                               file_type: str, file_size: int, course_name: str, 
                               course_code: str, uploaded_by: int) -> Optional[int]:
        """Create a new course material entry"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO course_materials 
                    (filename, original_filename, file_path, file_type, file_size, 
                     course_name, course_code, uploaded_by, status)
                    VALUES (:filename, :original_filename, :file_path, :file_type, :file_size,
                            :course_name, :course_code, :uploaded_by, 'pending')
                """), {
                    "filename": filename,
                    "original_filename": original_filename,
                    "file_path": file_path,
                    "file_type": file_type,
                    "file_size": file_size,
                    "course_name": course_name,
                    "course_code": course_code,
                    "uploaded_by": uploaded_by
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating course material: %s", e)
            return None
    
    def get_course_materials(self, course_code: str = None, uploaded_by: int = None) -> List[Dict]:
        """Get course materials with optional filtering"""
        try:
            with self.engine.connect() as conn:
                query = """
                    SELECT cm.material_id, cm.filename, cm.original_filename, cm.file_path,
                           cm.file_type, cm.file_size, cm.course_name, cm.course_code,
                           cm.uploaded_by, cm.upload_date, cm.processed, cm.status, cm.chunk_count,
                           u.username as uploader_name
                    FROM course_materials cm
                    LEFT JOIN users u ON cm.uploaded_by = u.user_id
                    WHERE 1=1
                """
                params = {}
                
                if course_code:
                    query += " AND cm.course_code = :course_code"
                    params["course_code"] = course_code
                
                if uploaded_by:
                    query += " AND cm.uploaded_by = :uploaded_by"
                    params["uploaded_by"] = uploaded_by
                
                query += " ORDER BY cm.upload_date DESC"
                
                result = conn.execute(text(query), params)
                materials = []
                for row in result:
                    materials.append({
                        "material_id": row[0],
                        "filename": row[1],
                        "original_filename": row[2],
                        "file_path": row[3],
                        "file_type": row[4],
                        "file_size": row[5],
                        "course_name": row[6],
                        "course_code": row[7],
                        "uploaded_by": row[8],
                        "upload_date": row[9],
                        "processed": row[10],
                        "status": row[11],
                        "chunk_count": row[12],
                        "uploader_name": row[13]
                    })
                return materials
        except Exception as e:
            logger.error("Error getting course materials: %s", e)
            return []
    
    def update_material_status(self, material_id: int, status: str, chunk_count: int = None) -> bool:
        """Update material processing status"""
        try:
            with self.engine.connect() as conn:
                query = "UPDATE course_materials SET status = :status, processed = :processed"
                params = {
                    "material_id": material_id,
                    "status": status,
                    "processed": status == 'ready'
                }
                
                if chunk_count is not None:
                    query += ", chunk_count = :chunk_count"
                    params["chunk_count"] = chunk_count
                
                query += " WHERE material_id = :material_id"
                
                result = conn.execute(text(query), params)
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error("Error updating material status: %s", e)
            return False
    
    def create_document_chunk(self, material_id: int, chunk_index: int, chunk_text: str,
                             page_number: int, token_count: int, embedding_id: str) -> Optional[int]:
        """Create a document chunk entry"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO document_chunks 
                    (material_id, chunk_index, chunk_text, page_number, token_count, embedding_id)
                    VALUES (:material_id, :chunk_index, :chunk_text, :page_number, :token_count, :embedding_id)
                """), {
                    "material_id": material_id,
                    "chunk_index": chunk_index,
                    "chunk_text": chunk_text,
                    "page_number": page_number,
                    "token_count": token_count,
                    "embedding_id": embedding_id
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating document chunk: %s", e)
            return None
    
    def get_document_chunks(self, material_id: int) -> List[Dict]:
        """Get all chunks for a material"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT chunk_id, material_id, chunk_index, chunk_text, 
                           page_number, token_count, embedding_id, created_at
                    FROM document_chunks
                    WHERE material_id = :material_id
                    ORDER BY chunk_index
                """), {"material_id": material_id})
                
                chunks = []
                for row in result:
                    chunks.append({
                        "chunk_id": row[0],
                        "material_id": row[1],
                        "chunk_index": row[2],
                        "chunk_text": row[3],
                        "page_number": row[4],
                        "token_count": row[5],
                        "embedding_id": row[6],
                        "created_at": row[7]
                    })
                return chunks
        except Exception as e:
            logger.error("Error getting document chunks: %s", e)
            return []
    
    def delete_course_material(self, material_id: int) -> bool:
        """Delete a course material and its chunks"""
        try:
            with self.engine.connect() as conn:
                # Chunks will be deleted automatically due to CASCADE
                result = conn.execute(text("""
                    DELETE FROM course_materials WHERE material_id = :material_id
                """), {"material_id": material_id})
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error("Error deleting course material: %s", e)
            return False
    
    def log_rag_query(self, user_id: int, query_text: str, course_code: str, 
                     chunks_retrieved: int, response_generated: bool) -> Optional[int]:
        """Log a RAG query for analytics"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO rag_queries 
                    (user_id, query_text, course_code, chunks_retrieved, response_generated)
                    VALUES (:user_id, :query_text, :course_code, :chunks_retrieved, :response_generated)
                """), {
                    "user_id": user_id,
                    "query_text": query_text,
                    "course_code": course_code,
                    "chunks_retrieved": chunks_retrieved,
                    "response_generated": response_generated
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error logging RAG query: %s", e)
            return None
    
    def create_course(self, course_code: str, course_name: str, description: str, instructor_id: int) -> Optional[int]:
        """Create a new course"""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO courses (course_code, course_name, description, instructor_id)
                    VALUES (:course_code, :course_name, :description, :instructor_id)
                """), {
                    "course_code": course_code,
                    "course_name": course_name,
                    "description": description,
                    "instructor_id": instructor_id
                })
                return result.lastrowid
        except Exception as e:
            logger.error("Error creating course: %s", e)
            return None
    
    def get_courses(self, instructor_id: int = None) -> List[Dict]:
        """Get all courses or courses by instructor"""
        try:
            with self.engine.connect() as conn:
                query = """
                    SELECT c.course_id, c.course_code, c.course_name, c.description,
                           c.instructor_id, c.created_at, c.active,
                           u.username as instructor_name,
                           COUNT(DISTINCT cm.material_id) as material_count
                    FROM courses c
                    LEFT JOIN users u ON c.instructor_id = u.user_id
                    LEFT JOIN course_materials cm ON c.course_code = cm.course_code
                    WHERE c.active = TRUE
                """
                params = {}
                
                if instructor_id:
                    query += " AND c.instructor_id = :instructor_id"
                    params["instructor_id"] = instructor_id
                
                query += " GROUP BY c.course_id ORDER BY c.created_at DESC"
                
                result = conn.execute(text(query), params)
                courses = []
                for row in result:
                    courses.append({
                        "course_id": row[0],
                        "course_code": row[1],
                        "course_name": row[2],
                        "description": row[3],
                        "instructor_id": row[4],
                        "created_at": row[5],
                        "active": row[6],
                        "instructor_name": row[7],
                        "material_count": row[8]
                    })
                return courses
        except Exception as e:
            logger.error("Error getting courses: %s", e)
            return []
    
    # ==================== SYSTEM SETTINGS (TOKEN LIMITS) ====================
    
    def get_system_setting(self, key: str, default: str = None) -> Optional[str]:
        """Get a system setting value"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT setting_value FROM system_settings WHERE setting_key = :key
                """), {"key": key})
                row = result.fetchone()
                return row[0] if row else default
        except Exception as e:
            logger.error("Error getting system setting {key}: %s", e)
            return default
    
    def set_system_setting(self, key: str, value: str, admin_id: int = None) -> bool:
        """Set a system setting value"""
        try:
            with self.engine.connect() as conn:
                # Check if setting exists
                result = conn.execute(text("""
                    SELECT setting_id FROM system_settings WHERE setting_key = :key
                """), {"key": key})
                
                if result.fetchone():
                    # Update existing - only set updated_by if admin_id is valid
                    if admin_id:
                        conn.execute(text("""
                            UPDATE system_settings 
                            SET setting_value = :value, updated_by = :admin_id
                            WHERE setting_key = :key
                        """), {"key": key, "value": value, "admin_id": admin_id})
                    else:
                        conn.execute(text("""
                            UPDATE system_settings 
                            SET setting_value = :value
                            WHERE setting_key = :key
                        """), {"key": key, "value": value})
                else:
                    # Insert new
                    if admin_id:
                        conn.execute(text("""
                            INSERT INTO system_settings (setting_key, setting_value, updated_by)
                            VALUES (:key, :value, :admin_id)
                        """), {"key": key, "value": value, "admin_id": admin_id})
                    else:
                        conn.execute(text("""
                            INSERT INTO system_settings (setting_key, setting_value)
                            VALUES (:key, :value)
                        """), {"key": key, "value": value})
                
                conn.commit()
                logger.info("System setting '%s' updated to: %s", key, value)
                return True
        except Exception as e:
            logger.error("Error setting system setting {key}: %s", e)
            return False
    
    def get_global_token_limit(self) -> int:
        """Get the global token limit for students"""
        try:
            value = self.get_system_setting('global_token_limit', '100000')
            return int(value)
        except Exception as e:
            logger.warning("Could not read global_token_limit, using default: %s", e)
            return 100000

    def get_guest_token_limit(self) -> int:
        """Get the token limit for guest users"""
        try:
            value = self.get_system_setting('guest_token_limit', '5000')
            return int(value)
        except Exception as e:
            logger.warning("Could not read guest_token_limit, using default: %s", e)
            return 5000
    
    def set_global_token_limit(self, limit: int, admin_id: int = None) -> bool:
        """Set the global token limit for all students"""
        return self.set_system_setting('global_token_limit', str(limit), admin_id)
    
    def set_guest_token_limit(self, limit: int, admin_id: int = None) -> bool:
        """Set the token limit for guest users"""
        return self.set_system_setting('guest_token_limit', str(limit), admin_id)
    
    def update_all_student_limits(self, new_limit: int) -> bool:
        """Update token limits for ALL students (force update)"""
        try:
            with self.engine.connect() as conn:
                # Update ALL students' token limits to the new global limit
                conn.execute(text("""
                    UPDATE token_limits tl
                    JOIN users u ON tl.user_id = u.user_id
                    SET tl.max_tokens = :new_limit
                    WHERE u.role = 'STUDENT'
                """), {"new_limit": new_limit})
                
                conn.commit()
                logger.info("Updated ALL student token limits to %s", new_limit)
                return True
        except Exception as e:
            logger.error("Error updating student limits: %s", e)
            return False
    
    def set_user_custom_token_limit(self, user_id: int, limit: int) -> bool:
        """Set a custom token limit for a specific user."""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    SELECT limit_id FROM token_limits
                    WHERE user_id = :user_id
                    ORDER BY period_start DESC
                    LIMIT 1
                """), {"user_id": user_id})

                row = result.fetchone()
                if row:
                    conn.execute(text("""
                        UPDATE token_limits SET max_tokens = :limit WHERE limit_id = :limit_id
                    """), {"limit": limit, "limit_id": row[0]})
                else:
                    conn.execute(text("""
                        INSERT INTO token_limits (user_id, max_tokens, period_start, period_end)
                        VALUES (:user_id, :limit, NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY))
                    """), {"user_id": user_id, "limit": limit})

            logger.info("Set custom token limit for user %s: %s", user_id, limit)
            return True
        except Exception as e:
            logger.error("Error setting custom token limit for user %s: %s", user_id, e)
            return False

# Global database manager instance
db_manager = DatabaseManager()

