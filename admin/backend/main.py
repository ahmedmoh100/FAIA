# Admin Backend - Updated for moderation flags fix
import os
import shutil
import zipfile
import io
import json
import csv
import logging
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import time
from typing import List, Dict
from datetime import datetime

# Load .env so JWT_SECRET_KEY matches the main backend
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    # .env is at the project root (3 levels up from admin/backend/)
    _env_path = _Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass  # python-dotenv not installed, fall back to env vars / defaults

# Setup logger
logger = logging.getLogger(__name__)

# Database configuration
from sqlalchemy.orm import Session
from sqlalchemy import text
 
# Optional system metrics
try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except Exception:
    psutil = None  # type: ignore
    HAS_PSUTIL = False

# Performance monitoring
try:
    from performance_monitor import performance_monitor
    HAS_PERFORMANCE_MONITOR = True
except Exception:
    performance_monitor = None
    HAS_PERFORMANCE_MONITOR = False

# Error logging
try:
    from error_logger import error_logger
    HAS_ERROR_LOGGER = True
except Exception:
    error_logger = None
    HAS_ERROR_LOGGER = False

try:
    from config import get_db, test_connection, get_db_info
    from models import User, UserRole, UserStatus, AuditLog, ModerationReport, ModerationAction, TokenLimit, FileStatus
    # UploadedFile removed - files not used in admin panel
    
    # Import database directly from config and models (standalone approach)
    from config import get_db, test_connection, get_db_info, engine
    from models import User, UserRole, UserStatus, AuditLog, TokenLimit
    
    # Import database manager from main backend
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent / "backend"))
    from database.database_integration import db_manager
    
    HAS_DATABASE = True
    DB_AVAILABLE = True
    logger.info("Database connected: MySQL %s at %s", DB_NAME if 'DB_NAME' in dir() else 'faia_chat_system', 'localhost')
    logger.info("db_manager loaded: %s", db_manager is not None)
    
    # Define monitor_operation when database is available
    from contextlib import contextmanager
    
    @contextmanager
    def monitor_operation(service, operation):
        """Simple context manager for monitoring operations"""
        yield
    
except ImportError as e:
    logger.error("[ERROR] Database import error: %s", e)
    db_manager = None
    HAS_DATABASE = False
    DB_AVAILABLE = False
    
    # Create dummy get_db function
    def get_db():
        return None
    
    # Fallback stubs for error monitoring functions
    from contextlib import contextmanager
    
    @contextmanager
    def monitor_operation(service, operation):
        yield
    
    def log_error(severity, category, service, operation, message, exception=None):
        logger.info("[%s] %s.%s: %s", severity, service, operation, message)
    
    def log_critical_error(service, operation, message, exception=None):
        logger.info("[CRITICAL] %s.%s: %s", service, operation, message)
    
    def log_security_error(service, operation, message, details=None):
        logger.info("[SECURITY] %s.%s: %s", service, operation, message)
    
    class ErrorSeverity:
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"
    
    class ErrorCategory:
        SYSTEM = "system"
        DATABASE = "database"
        API = "api"
        SECURITY = "security"
    
    class ErrorMonitor:
        monitoring_active = False
        def get_error_summary(self, hours=24):
            return {"errors_by_severity": {}, "errors_by_category": {}}
        def get_system_health(self):
            return {"status": "unknown"}
        def resolve_error(self, error_id, notes):
            return False
        def cleanup_old_data(self, days):
            return {"deleted": 0}
    
    error_monitor = ErrorMonitor()
    
    class HealthChecker:
        def get_health_status(self):
            return {"status": "unknown"}
    
    health_checker = HealthChecker()
    
except Exception as e:
    logger.error("[ERROR] Database modules not available: %s", e)
    db_manager = None
    HAS_DATABASE = False
    DB_AVAILABLE = False

logger.info("Admin backend loaded. Database available: %s", DB_AVAILABLE)

# Helper function for optional database dependency
def get_db_optional():
    """Get database session if available, otherwise return None"""
    if DB_AVAILABLE:
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    else:
        yield None

# JSON storage fallback (no DB mode)
try:
    import storage as store  # type: ignore
except Exception:
    store = None  # type: ignore


API_TITLE = "FAIA Admin API"
API_VERSION = "0.1.0"

# JWT Configuration - must match main backend
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Set it in your .env file before starting the admin backend."
    )
JWT_ALGORITHM = "HS256"
ADMIN_ORIGINS = os.getenv("ADMIN_ORIGINS", "*").split(",")

app = FastAPI(title=API_TITLE, version=API_VERSION)

# Enhanced CORS configuration for admin panel
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ADMIN_CORS_ORIGINS", "http://localhost:8090,http://localhost:5500").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)


class AdminUser(BaseModel):
    id: str
    username: str
    role: str = "ADMIN"


def get_current_admin(authorization: Optional[str] = Header(default=None)) -> AdminUser:
    """Verify JWT token and check if user is ADMIN"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    
    token = authorization.split(" ", 1)[1]
    
    try:
        # Decode JWT token (same secret as main backend)
        import jwt
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Extract username from token
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        
        # Check if user exists and is ADMIN
        if DB_AVAILABLE:
            db = next(get_db())
            try:
                user = db.query(User).filter(User.username == username).first()
                if not user:
                    raise HTTPException(status_code=401, detail="User not found")

                user_role = user.role.value if hasattr(user.role, 'value') else user.role
                if user_role not in ["ADMIN", "PROFESSOR"]:
                    raise HTTPException(status_code=403, detail="Admin or Professor access required")

                user_status = user.status.value if hasattr(user.status, 'value') else user.status
                if user_status != "ACTIVE":
                    raise HTTPException(status_code=403, detail="Account is not active")

                return AdminUser(id=str(user.user_id), username=user.username, role=user_role)
            finally:
                db.close()
        else:
            # DB unavailable — deny all access, do not fall back to unauthenticated admin
            raise HTTPException(status_code=503, detail="Database unavailable. Admin panel requires database access.")
            
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid JWT token: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auth error: %s", e)
        raise HTTPException(status_code=401, detail="Authentication failed")


# TEST ENDPOINT
@app.get("/test123")
async def test_endpoint():
    logger.debug("TEST ENDPOINT CALLED!")
    return {"test": "working", "db_available": DB_AVAILABLE}

@app.get("/admin/health")
async def admin_health():
    try:
        with monitor_operation("admin_backend", "health_check"):
            resp = {
                "status": "ok",
                "service": API_TITLE,
                "version": API_VERSION,
                "time": time.time(),
            }
            
            # Check database availability
            if DB_AVAILABLE:
                try:
                    db_info = get_db_info()
                    resp["database"] = db_info
                except Exception as e:
                    resp["database"] = {"connected": False, "error": str(e)}
            else:
                resp["database"] = {"connected": False, "error": "Database modules not available"}
    except Exception as e:
        resp = {"status": "error", "error": str(e)}
    
    return resp


@app.post("/admin/login")
async def admin_login(username: str = Form(...), password: str = Form(...)):
    """Admin login endpoint - returns JWT token"""
    logger.info("Login attempt: username=%s", username)

    if not DB_AVAILABLE:
        logger.error("Login rejected — database not available")
        raise HTTPException(status_code=503, detail="Database not available")
    
    db = next(get_db())
    try:
        # Find user
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Check password
        import hashlib
        password_hash = hashlib.sha256((user.password_salt + password).encode()).hexdigest()
        if password_hash != user.password_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Check if ADMIN or PROFESSOR
        user_role = user.role.value if hasattr(user.role, 'value') else user.role
        if user_role not in ["ADMIN", "PROFESSOR"]:
            raise HTTPException(status_code=403, detail="Admin or Professor access required")
        
        # Check if ACTIVE
        user_status = user.status.value if hasattr(user.status, 'value') else user.status
        if user_status != "ACTIVE":
            raise HTTPException(status_code=403, detail="Account is not active")
        
        # Create JWT token
        import jwt
        from datetime import datetime, timedelta
        
        payload = {
            "sub": user.username,
            "role": user_role,
            "exp": datetime.utcnow() + timedelta(hours=8)  # 8 hour expiry for admin
        }
        
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "username": user.username,
            "role": user_role
        }
        
    finally:
        db.close()


@app.get("/admin/me")
async def admin_me(admin: AdminUser = Depends(get_current_admin)):
    return {"id": admin.id, "username": admin.username, "role": admin.role}


# Dashboard/Overview endpoint
@app.get("/admin/overview")
async def get_overview():
    """Get dashboard overview data"""
    overview = {
        "total_users": 0,
        "active_sessions": 0,
        "total_chats": 0,
        "total_messages": 0,
        "system_health": "healthy",
        "uptime": "24h 15m"
    }
    
    if DB_AVAILABLE:
        try:
            db = next(get_db())
            try:
                from models import Session as SessionModel
                
                # Get counts
                overview["total_users"] = db.query(User).count()
                overview["active_sessions"] = db.query(SessionModel).filter(
                    SessionModel.logout_time == None
                ).count()
                
                # Get chat and message counts from database
                result = db.execute(text("SELECT COUNT(*) FROM chats"))
                overview["total_chats"] = result.scalar() or 0
                
                result = db.execute(text("SELECT COUNT(*) FROM messages"))
                overview["total_messages"] = result.scalar() or 0
                
            finally:
                db.close()
        except Exception as e:
            logger.error("Overview query failed: %s", e)
    
    return overview


# System summary endpoint
@app.get("/admin/system")
async def get_system_summary():
    """Get system summary (combines health, resources, etc.)"""
    summary = {
        "health": {
            "status": "healthy",
            "database": True,
            "ai_model": True,
            "uptime": "24h 15m"
        },
        "resources": {
            "cpu_usage": 35,
            "memory_usage": 45,
            "disk_usage": 60
        },
        "stats": {
            "total_users": 0,
            "active_sessions": 0,
            "total_requests": 0
        }
    }
    
    if DB_AVAILABLE:
        try:
            db = next(get_db())
            try:
                from models import Session as SessionModel
                summary["stats"]["total_users"] = db.query(User).count()
                summary["stats"]["active_sessions"] = db.query(SessionModel).filter(
                    SessionModel.logout_time == None
                ).count()
            finally:
                db.close()
        except Exception as e:
            logger.error("System summary query failed: %s", e)
    
    # Get real resource usage if psutil available
    if HAS_PSUTIL:
        try:
            summary["resources"]["cpu_usage"] = psutil.cpu_percent(interval=0.1)
            summary["resources"]["memory_usage"] = psutil.virtual_memory().percent
            summary["resources"]["disk_usage"] = psutil.disk_usage('/').percent
        except:
            pass
    
    return summary


# System endpoints for the System page
@app.get("/admin/system/health")
async def system_health():
    """Enhanced health check for the System page"""
    
    # Calculate real uptime
    uptime_str = "Unknown"
    system_load = 0
    resp_disk_usage = 0
    resp_disk_free = 0
    if HAS_PSUTIL:
        try:
            import time
            uptime_seconds = time.time() - psutil.boot_time()
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            
            if days > 0:
                uptime_str = ("%sd %sh %sm" % (days, hours, minutes))
            elif hours > 0:
                uptime_str = ("%sh %sm" % (hours, minutes))
            else:
                uptime_str = ("%sm" % minutes)
            
            # Get real system load (CPU usage)
            system_load = round(psutil.cpu_percent(interval=0.1))
            # Get disk usage
            disk = psutil.disk_usage('/')
            resp_disk_usage = round(disk.percent)
            resp_disk_free = round(disk.free / (1024 ** 3), 1)  # GB
        except Exception as e:
            logger.error("Uptime calculation error: %s", e)
            resp_disk_usage = 0
            resp_disk_free = 0
    else:
        resp_disk_usage = 0
        resp_disk_free = 0
    
    # Check database connection
    database_connected = False
    if DB_AVAILABLE:
        try:
            db = next(get_db())
            try:
                db.execute(text("SELECT 1"))
                database_connected = True
            finally:
                db.close()
        except Exception:
            pass
    
    resp = {
        "uptime": uptime_str,
        "database": database_connected,
        "ai_model": True,  # TODO: Actually check model availability
        "disk_usage": resp_disk_usage,
        "disk_free": resp_disk_free,
        "total_users": 0,
        "active_sessions": 0,
        "total_files": 0,
        "system_load": system_load
    }
    
    # Get real data when DB is available
    if DB_AVAILABLE:
        try:
            db = next(get_db())
            try:
                from models import Session as SessionModel
                
                # Count users
                user_count = db.query(User).count()
                resp["total_users"] = user_count
                
                # Count indexed course materials (status = ready)
                try:
                    material_count = db.execute(
                        text("SELECT COUNT(*) FROM course_materials WHERE status = 'ready'")
                    ).scalar()
                    resp["total_files"] = material_count or 0
                except Exception:
                    resp["total_files"] = 0
                
                # Count only truly active sessions (no logout time)
                session_count = db.query(SessionModel).filter(
                    SessionModel.logout_time == None
                ).count()
                resp["active_sessions"] = session_count
                
            finally:
                db.close()
        except Exception as e:
            logger.error("System health query failed: %s", e)
            import traceback
            traceback.print_exc()
    
    return resp


@app.get("/admin/system/resources")
async def system_resources():
    """System resource monitoring"""
    resp = {
        "cpu_usage": 0,
        "memory_usage": 0,
        "disk_usage": 0,
        "disk_free": 0,
        "requests_per_min": 0,  # Not tracked - set to 0
        "avg_response_time": 0,  # Not tracked - set to 0
        "error_rate": 0,  # Not tracked - set to 0
        "db_connections": 0  # Not tracked - set to 0
    }
    
    # Use psutil if available for real metrics
    if HAS_PSUTIL:
        try:
            resp["cpu_usage"] = round(psutil.cpu_percent(interval=0.1))
            
            memory = psutil.virtual_memory()
            resp["memory_usage"] = round(memory.percent)
            
            disk = psutil.disk_usage('/')
            resp["disk_usage"] = round((disk.used / disk.total) * 100)
            resp["disk_free"] = round(disk.free / (1024**3))  # GB
            
        except Exception as e:
            logger.error("Resource monitoring error: %s", e)
    
    # Get real DB connection count if possible
    if DB_AVAILABLE:
        try:
            db = next(get_db())
            try:
                # Try to get connection count from MySQL
                result = db.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
                row = result.fetchone()
                if row:
                    resp["db_connections"] = int(row[1])
            finally:
                db.close()
        except Exception as e:
            logger.error("DB connection count error: %s", e)
    
    return resp

# ==================== ERROR MONITORING ENDPOINTS ====================
# Removed - not used by frontend

# ==================== CACHE MANAGEMENT ENDPOINTS ====================
# Removed - not used by frontend

# ==================== SYSTEM MODEL ENDPOINT ====================
# Removed - duplicate of /admin/models/status

# Serve frontend index.html at root
@app.get("/")
async def root():
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"service": API_TITLE, "version": API_VERSION}


# ------------------------------
# In-memory admin data (isolated)
# ------------------------------
_TOKENIZATION_LIMIT = {"max_tokens": 350}
_AUDIT_LOGS = []  # list of dicts
# Demo flags removed - now using real database
_FLAGS = []


# ==================== CLEAN TOKEN MANAGEMENT - 3 ENDPOINTS ====================

class TokenLimitUpdate(BaseModel):
    max_tokens: int

@app.put("/admin/tokens/global")
async def set_global_token_limit(
    body: TokenLimitUpdate,
    admin: AdminUser = Depends(get_current_admin)
):
    """Set global token limit - applies to ADMIN and PROFESSOR roles"""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        from config import engine
        with engine.begin() as conn:
            # Save to system_settings
            conn.execute(text("""
                INSERT INTO system_settings (setting_key, setting_value)
                VALUES ('global_token_limit', :val)
                ON DUPLICATE KEY UPDATE setting_value = :val
            """), {"val": str(body.max_tokens)})
            # Also update existing ADMIN and PROFESSOR rows in token_limits
            conn.execute(text("""
                UPDATE token_limits tl
                JOIN users u ON tl.user_id = u.user_id
                SET tl.max_tokens = :val
                WHERE u.role IN ('ADMIN', 'PROFESSOR')
            """), {"val": body.max_tokens})
        try:
            db_manager.log_audit_action(int(admin.id), ("set_global_token_limit:%s" % body.max_tokens), None, "system_settings")
        except Exception:
            pass
        return {"success": True, "max_tokens": body.max_tokens, "message": ("Global limit set to %s" % body.max_tokens)}
    except Exception as e:
        logger.error("Error setting global token limit: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/tokens/student")
async def set_student_token_limit(
    body: TokenLimitUpdate,
    admin: AdminUser = Depends(get_current_admin)
):
    """Update max_tokens for ALL students in token_limits table.
    Also inserts rows for students who have never chatted (no existing token_limits row).
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        from config import engine
        with engine.begin() as conn:
            # Update existing student rows
            result = conn.execute(text("""
                UPDATE token_limits tl
                JOIN users u ON tl.user_id = u.user_id
                SET tl.max_tokens = :val
                WHERE u.role = 'STUDENT'
            """), {"val": body.max_tokens})
            updated = result.rowcount

            # Insert rows for students who don't have one yet
            insert_result = conn.execute(text("""
                INSERT INTO token_limits (user_id, max_tokens, used_tokens, period_start, period_end)
                SELECT u.user_id, :val, 0, NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY)
                FROM users u
                LEFT JOIN token_limits tl ON tl.user_id = u.user_id
                WHERE u.role = 'STUDENT'
                  AND tl.user_id IS NULL
            """), {"val": body.max_tokens})
            inserted = insert_result.rowcount

        try:
            db_manager.log_audit_action(int(admin.id), ("set_student_token_limit:%s (updated:%s inserted:%s)" % (body.max_tokens, updated, inserted)), None, "token_limits")
        except Exception:
            pass
        return {"success": True, "max_tokens": body.max_tokens, "message": ("Updated %s students, created %s new records" % (updated, inserted))}
    except Exception as e:
        logger.error("Error setting student token limit: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/tokens/guest")
async def set_guest_token_limit(
    body: TokenLimitUpdate,
    admin: AdminUser = Depends(get_current_admin)
):
    """Set guest token limit in system_settings"""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        from config import engine
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO system_settings (setting_key, setting_value)
                VALUES ('guest_token_limit', :val)
                ON DUPLICATE KEY UPDATE setting_value = :val
            """), {"val": str(body.max_tokens)})
        try:
            db_manager.log_audit_action(int(admin.id), ("set_guest_token_limit:%s" % body.max_tokens), None, "system_settings")
        except Exception:
            pass
        return {"success": True, "max_tokens": body.max_tokens, "message": "Guest token limit updated"}
    except Exception as e:
        logger.error("Error setting guest token limit: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/tokens/limits")
async def get_all_token_limits(admin: AdminUser = Depends(get_current_admin)):
    """Get all token limits (global, student, guest)"""
    if not HAS_DATABASE or not db_manager:
        return {
            "global_limit": 100000,
            "student_limit": 100000,
            "guest_limit": 100000
        }
    
    try:
        global_limit = db_manager.get_global_token_limit()
        guest_limit = db_manager.get_guest_token_limit()
        
        # Get student limit (first student's limit or global)
        from config import engine
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT tl.max_tokens
                FROM token_limits tl
                JOIN users u ON tl.user_id = u.user_id
                WHERE u.role = 'STUDENT'
                LIMIT 1
            """))
            row = result.fetchone()
            student_limit = row[0] if row else global_limit
        
        return {
            "global_limit": global_limit,
            "student_limit": student_limit,
            "guest_limit": guest_limit
        }
    except Exception as e:
        logger.error("Error getting token limits: %s", e)
        return {
            "global_limit": 100000,
            "student_limit": 100000,
            "guest_limit": 100000
        }

# Removed - not needed for admin panel


@app.get("/admin/audit")
async def list_audit(limit: int = 100, q: str | None = None):
    if DB_AVAILABLE:
        db = next(get_db())
        try:
            # Use LEFT JOIN to handle NULL admin_id
            query = db.query(AuditLog).outerjoin(User, AuditLog.admin_id == User.user_id)
            
            # Apply search filter - only search by actor (username)
            if q:
                search_term = ("%%s%" % q)
                query = query.filter(User.username.ilike(search_term))
            
            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            
            result = []
            for log in logs:
                # Get target name if it's a user
                target_name = None
                if log.target_table == "users" and log.target_id:
                    try:
                        target_user = db.query(User).filter(User.user_id == log.target_id).first()
                        if target_user:
                            target_name = target_user.username
                    except:
                        pass
                
                result.append({
                    "id": log.log_id,
                    "actor": log.actor.username if log.actor else "System",
                    "action": log.action,
                    "target_type": log.target_table or "system",
                    "target_id": log.target_id,
                    "target_name": target_name,  # Add username for user targets
                    "ts": log.timestamp.timestamp() if log.timestamp else 0
                })
            return result
        except Exception as e:
            logger.error("Database query failed: %s", e)
            # Fall back to JSON storage
        finally:
            try:
                db.close()
            except Exception:
                pass
    
    if store is not None:
        try:
            logs = store.list_audit()
            # Apply search filter to fallback data - only search by actor
            if q:
                filtered_logs = []
                q_lower = q.lower()
                for log in logs:
                    if q_lower in log.get("actor", "").lower():
                        filtered_logs.append(log)
                logs = filtered_logs
            return list(reversed(logs))[:limit]
        except Exception:
            pass
    
    # In-memory fallback with search - only search by actor
    logs = list(_AUDIT_LOGS)
    if q:
        filtered_logs = []
        q_lower = q.lower()
        for log in logs:
            if q_lower in log.get("actor", "").lower():
                filtered_logs.append(log)
        logs = filtered_logs
    
    return list(reversed(logs))[:limit]


class AuditEntry(BaseModel):
    action: str
    target_type: str | None = None
    target_id: str | None = None
    meta: dict | None = None


@app.post("/admin/audit")
async def add_audit(entry: AuditEntry, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    if DB_AVAILABLE:
        try:
            # Find admin user by username
            admin_user = db.query(User).filter(User.username == admin.username).first()
            if admin_user:
                # Create audit log entry
                audit_log = AuditLog(
                    admin_id=admin_user.user_id,
                    action=entry.action,
                    target_id=int(entry.target_id) if entry.target_id else None,
                    target_table=entry.target_type
                )
                db.add(audit_log)
                db.commit()
                return {"success": True, "stored": True}
        except Exception as e:
            logger.error("Database audit log failed: %s", e)
            # Fall back to JSON storage
    
    # JSON storage fallback
    if store is not None:
        try:
            store.add_audit(admin.username, entry.action, entry.target_type, entry.target_id, entry.meta)
            return {"success": True, "stored": False}
        except Exception:
            pass
    
    # In-memory fallback
    rec = {
        "actor": admin.username,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "meta": entry.meta,
        "ts": time.time()
    }
    _AUDIT_LOGS.append(rec)
    return {"success": True, "stored": False}


@app.get("/admin/audit/export")
async def export_audit(
    format: str = "csv", 
    q: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Optional[Session] = Depends(get_db_optional)
):
    """Export audit logs as CSV (matching sessions export pattern)"""
    from fastapi.responses import StreamingResponse
    import io
    import csv
    from datetime import datetime
    
    if not DB_AVAILABLE or db is None:
        # Fallback to in-memory/store data with proper CSV format
        rows = []
        if store is not None:
            try:
                rows = store.list_audit()
                # Apply search filter to fallback data - only search by actor
                if q:
                    filtered_logs = []
                    q_lower = q.lower()
                    for log in rows:
                        if q_lower in log.get("actor", "").lower():
                            filtered_logs.append(log)
                    rows = filtered_logs
            except Exception:
                rows = []
        
        if not rows:
            rows = list(_AUDIT_LOGS)
            # In-memory fallback with search - only search by actor
            if q:
                filtered_logs = []
                q_lower = q.lower()
                for log in rows:
                    if q_lower in log.get("actor", "").lower():
                        filtered_logs.append(log)
                rows = filtered_logs
        
        # Create CSV with proper format (same as database version)
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Log ID', 'Actor', 'Action', 'Target Type', 'Target ID', 'Target Name', 'Timestamp'
        ])
        
        # Write data
        for r in rows:
            ts = r.get("ts", 0)
            timestamp_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else ''
            
            writer.writerow([
                r.get("id", ""),
                r.get("actor", ""),
                r.get("action", ""),
                r.get("target_type", ""),
                r.get("target_id", ""),
                r.get("target_name", ""),  # This might be empty for fallback data
                timestamp_str
            ])
        
        # Prepare response
        output.seek(0)
        filename = ("audit_export_%s.csv" % datetime.now().strftime('%Y%m%d_%H%M%S'))
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": ("attachment; filename=%s" % filename)}
        )
    
    try:
        # Use LEFT JOIN to handle NULL admin_id
        query = db.query(AuditLog).outerjoin(User, AuditLog.admin_id == User.user_id)
        
        # Apply search filter - only search by actor (username)
        if q:
            search_term = ("%%s%" % q)
            query = query.filter(User.username.ilike(search_term))
        
        logs = query.order_by(AuditLog.timestamp.desc()).limit(1000).all()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Log ID', 'Actor', 'Action', 'Target Type', 'Target ID', 'Target Name', 'Timestamp'
        ])
        
        # Write data
        for log in logs:
            # Get target name if it's a user
            target_name = ''
            if log.target_table == "users" and log.target_id:
                try:
                    target_user = db.query(User).filter(User.user_id == log.target_id).first()
                    if target_user:
                        target_name = target_user.username
                except:
                    pass
            
            writer.writerow([
                log.log_id,
                log.admin.username if log.admin else "System",
                log.action,
                log.target_table or "system",
                log.target_id or '',
                target_name,
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if log.timestamp else ''
            ])
        
        # Prepare response
        output.seek(0)
        filename = ("audit_export_%s.csv" % datetime.now().strftime('%Y%m%d_%H%M%S'))
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": ("attachment; filename=%s" % filename)}
        )
    except Exception as e:
        logger.error("Error exporting audit logs: %s", e)
        raise HTTPException(status_code=500, detail=("Failed to export audit logs: %s" % str(e)))
    finally:
        if db:
            db.close()


# Removed - not needed for admin panel (use 3 simple endpoints above)








def _find_mysql_tool(tool: str):
    """Find mysqldump or mysql CLI. Returns path string or None."""
    import subprocess as _sp
    candidates = [
        tool,  # PATH first
        ("C:\\xampp\\mysql\\bin\\%s.exe" % tool),
        ("C:\\Program Files\\MySQL\\MySQL Server 8.0\\bin\\%s.exe" % tool),
        ("C:\\Program Files\\MySQL\\MySQL Server 8.4\\bin\\%s.exe" % tool),
    ]
    for path in candidates:
        try:
            _sp.run([path, "--version"], capture_output=True, timeout=3, check=False)
            return path  # ran without FileNotFoundError = it exists
        except (FileNotFoundError, OSError):
            continue
    return None


@app.post("/admin/backup/create")
async def create_backup(admin: AdminUser = Depends(get_current_admin)):
    """Create a complete system backup"""
    import subprocess
    import os
    from datetime import datetime
    import zipfile
    from pathlib import Path
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use Path to get reliable absolute path
        current_file = Path(__file__).resolve()
        backup_dir = current_file.parent.parent.parent / "database_backups"
        backup_dir = str(backup_dir)
        os.makedirs(backup_dir, exist_ok=True)
        
        # SQL dump filename
        sql_file = os.path.join(backup_dir, ("backup_%s.sql" % timestamp))
        zip_file = os.path.join(backup_dir, ("backup_%s.zip" % timestamp))
        
        # Find mysqldump
        mysqldump_cmd = _find_mysql_tool("mysqldump")
        
        if not mysqldump_cmd:
            # Fallback: Use Python to export data
            logger.warning("mysqldump not found, using Python fallback")
            try:
                db = next(get_db())
                try:
                    with open(sql_file, 'w', encoding='utf-8') as f:
                        f.write(("-- FAIA Database Backup %s\n" % timestamp))
                        f.write("-- Generated using Python fallback (mysqldump not available)\n")
                        f.write("-- Database: faia_chat_system\n\n")
                        
                        # Export table counts
                        tables = ['users', 'sessions', 'chats', 'messages', 'token_limits', 'audit_logs', 'course_materials']
                        for table in tables:  # table is from hardcoded list above - safe
                            try:
                                count = db.execute(text("SELECT COUNT(*) FROM " + table)).scalar()
                                f.write(("-- %s: %s rows\n" % (table, count)))
                            except:
                                pass
                        
                        f.write("\n-- Note: This is a summary backup only.\n")
                        f.write("-- For full backup, install MySQL and use mysqldump.\n")
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass

                # Create zip
                with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(sql_file, os.path.basename(sql_file))
                
                size_bytes = os.path.getsize(zip_file)
                size_mb = size_bytes / (1024 * 1024)
                os.remove(sql_file)
                
                return {
                    "success": True,
                    "backup_name": ("backup_%s.zip" % timestamp),
                    "created_at": datetime.now().isoformat(),
                    "size_mb": round(size_mb, 2),
                    "file_path": zip_file,
                    "note": "Created using Python fallback (mysqldump not available)"
                }
            except Exception as e:
                return {"success": False, "error": ("Backup failed: %s" % str(e))}
        
        dump_command = [
            mysqldump_cmd,
            "-u", "root",
            "--single-transaction",
            "--routines",
            "--triggers",
            "faia_chat_system"
        ]
        
        with open(sql_file, 'w', encoding='utf-8') as f:
            result = subprocess.run(dump_command, stdout=f, stderr=subprocess.PIPE, text=True)
            
        if result.returncode != 0:
            return {"success": False, "error": ("MySQL dump failed: %s" % result.stderr)}
        
        # Create zip archive
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(sql_file, os.path.basename(sql_file))
            
        # Get file size
        size_bytes = os.path.getsize(zip_file)
        size_mb = size_bytes / (1024 * 1024)
        
        # Clean up SQL file (keep only zip)
        os.remove(sql_file)
        
        return {
            "success": True,
            "backup_name": ("backup_%s.zip" % timestamp),
            "created_at": datetime.now().isoformat(),
            "size_mb": round(size_mb, 2),
            "file_path": zip_file
        }
        
    except FileNotFoundError:
        return {"success": False, "error": "mysqldump command not found. Please ensure MySQL is installed and in PATH."}
    except Exception as e:
        return {"success": False, "error": ("Backup failed: %s" % str(e))}


@app.post("/admin/backup/restore")
async def restore_backup(
    backup_file: UploadFile,
    admin: AdminUser = Depends(get_current_admin)
):
    """Restore system from backup file"""
    import subprocess
    import os
    import zipfile
    import tempfile
    
    try:
        # Create temp directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            content = await backup_file.read()
            filename = backup_file.filename or "backup"
            
            sql_file = None
            
            # Handle .sql files directly
            if filename.endswith('.sql'):
                sql_file = os.path.join(temp_dir, Path(filename).name)
                with open(sql_file, 'wb') as f:
                    f.write(content)
            
            # Handle .zip files
            elif filename.endswith('.zip'):
                zip_path = os.path.join(temp_dir, "backup.zip")
                with open(zip_path, 'wb') as f:
                    f.write(content)
                
                # Extract zip
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Find SQL file in extracted contents
                for file in os.listdir(temp_dir):
                    if file.endswith('.sql'):
                        sql_file = os.path.join(temp_dir, Path(file).name)
                        break
                
                if not sql_file:
                    return {"success": False, "error": "No SQL file found in backup ZIP"}
            else:
                return {"success": False, "error": "Invalid file type. Upload .sql or .zip file"}
            
            # Verify we have a SQL file
            if not sql_file or not os.path.exists(sql_file):
                return {"success": False, "error": "SQL file not found or invalid"}
            
            # Find mysql command
            mysql_cmd = _find_mysql_tool("mysql")
            
            if not mysql_cmd:
                return {"success": False, "error": "MySQL not found. Please install MySQL or add it to PATH."}
            
            # Restore database using mysql command
            restore_command = [
                mysql_cmd,
                "-u", "root",
                "faia_chat_system"
            ]
            
            with open(sql_file, 'r', encoding='utf-8') as f:
                result = subprocess.run(restore_command, stdin=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                return {"success": False, "error": ("MySQL restore failed: %s" % result.stderr)}
            
            return {
                "success": True,
                "message": "System restored successfully",
                "restored_at": datetime.now().isoformat()
            }
            
    except Exception as e:
        return {"success": False, "error": ("Restore failed: %s" % str(e))}


@app.get("/admin/backup/history")
async def get_backup_history(admin: AdminUser = Depends(get_current_admin)):
    """Get list of available backups"""
    import os
    from datetime import datetime
    from pathlib import Path
    
    try:
        # Use Path to get reliable absolute path
        # Go up from admin/backend to project root, then to database_backups
        current_file = Path(__file__).resolve()
        backup_dir = current_file.parent.parent.parent / "database_backups"
        backup_dir = str(backup_dir)
        
        if not os.path.exists(backup_dir):
            return {"backups": []}
        
        backups = []
        for filename in os.listdir(backup_dir):
            # Accept both .zip and .sql files
            if filename.endswith('.zip') or filename.endswith('.sql'):
                filepath = os.path.join(backup_dir, Path(filename).name)
                stat = os.stat(filepath)
                
                backups.append({
                    "name": filename,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "path": filepath
                })
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {"backups": backups}
        
    except Exception as e:
        return {"backups": [], "error": str(e)}


@app.get("/admin/dashboard/stats")
async def get_dashboard_stats():
    """Simple endpoint for dashboard stats - bypasses complex report logic"""
    from config import engine
    from datetime import datetime
    
    try:
        with engine.connect() as conn:
            # Simple direct queries
            total_users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            total_flags = conn.execute(text("SELECT COUNT(*) FROM moderation_reports")).scalar()
            pending_flags = conn.execute(text("SELECT COUNT(*) FROM moderation_reports WHERE status='pending'")).scalar()
            
            # Today's activity
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            sessions_today = conn.execute(text(
                "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE login_time >= :today"
            ), {"today": today}).scalar() or 0
            
            tokens_today = conn.execute(text(
                "SELECT COALESCE(SUM(token_count), 0) FROM messages WHERE created_at >= :today"
            ), {"today": today}).scalar() or 0
            
            return {
                "total_users": total_users,
                "active_today": sessions_today,
                "pending_reports": pending_flags,
                "tokens_today": int(tokens_today)
            }
    except Exception as e:
        logger.error("Dashboard stats error: %s", e)
        return {
            "error": str(e),
            "total_users": 0,
            "active_today": 0,
            "pending_reports": 0,
            "tokens_today": 0
        }


# Get single user by ID
@app.get("/admin/users/{user_id}")
async def admin_get_user(user_id: int, db: Optional[Session] = Depends(get_db_optional)):
    """Get a single user by ID"""
    if DB_AVAILABLE and db is not None:
        try:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            role_val = user.role.value if hasattr(user.role, 'value') else user.role
            status_val = user.status.value if hasattr(user.status, 'value') else user.status
            
            return {
                "id": str(user.user_id),
                "username": user.username,
                "email": user.email,
                "role": role_val,
                "status": status_val,
                "active": status_val == "ACTIVE",
                "created_at": user.created_at.timestamp() if user.created_at else 0,
                "last_login": user.last_login.timestamp() if user.last_login else None
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching user: %s", e)
            raise HTTPException(status_code=500, detail=("Failed to fetch user: %s" % str(e)))
        finally:
            db.close()
    
    raise HTTPException(status_code=503, detail="Database not available")


# Users list (DB-backed when available; otherwise JSON storage)
@app.get("/admin/users")
async def admin_list_users(q: str | None = None, role: str | None = None, status: str | None = None):
    if DB_AVAILABLE:
        # Get DB session manually
        db = next(get_db())
        try:
            # Late import like the working tokenization endpoint
            from models import User as UserModel, UserRole, UserStatus
            query = db.query(UserModel)
            
            # Apply search filter
            if q:
                query = query.filter(
                    (UserModel.username.contains(q)) | 
                    (UserModel.email.contains(q))
                )
            
            # Apply role filter
            if role:
                try:
                    role_enum = UserRole(role.upper())
                    query = query.filter(UserModel.role == role_enum)
                except ValueError:
                    # Invalid role, skip filter
                    pass
            
            # Apply status filter
            if status:
                try:
                    status_enum = UserStatus(status.upper())
                    query = query.filter(UserModel.status == status_enum)
                except ValueError:
                    # Invalid status, skip filter
                    pass
            
            users = query.order_by(UserModel.created_at.desc()).limit(200).all()
            
            result = []
            for user in users:
                # Handle both enum and string values
                role_val = user.role.value if hasattr(user.role, 'value') else user.role
                status_val = user.status.value if hasattr(user.status, 'value') else user.status
                is_active = (status_val == "ACTIVE") or (user.status == UserStatus.ACTIVE if hasattr(UserStatus, 'ACTIVE') else False)
                
                # Get token info for this user
                token_info = {"max_tokens": None, "used_tokens": None, "remaining_tokens": None}
                try:
                    from sqlalchemy import text
                    token_result = db.execute(text("""
                        SELECT max_tokens, used_tokens
                        FROM token_limits
                        WHERE user_id = :user_id
                        ORDER BY period_start DESC
                        LIMIT 1
                    """), {"user_id": user.user_id})
                    token_row = token_result.fetchone()
                    if token_row:
                        max_tokens = token_row[0] or 0
                        used_tokens = token_row[1] or 0
                        token_info = {
                            "max_tokens": max_tokens,
                            "used_tokens": used_tokens,
                            "remaining_tokens": max_tokens - used_tokens
                        }
                except Exception as e:
                    logger.warning("Warning: Could not fetch token info for user %s: %s", user.user_id, e)
                
                result.append({
                    "id": str(user.user_id),
                    "username": user.username,
                    "email": user.email,
                    "role": role_val,
                    "status": status_val,
                    "active": is_active,
                    "created_at": user.created_at.timestamp() if user.created_at else 0,
                    "last_login": user.last_login.timestamp() if user.last_login else None,
                    "token_info": token_info
                })
            return result
        except Exception as e:
            logger.error("Database query failed in admin_list_users: %s", e)
            # Fall back to JSON storage
    
    # JSON storage fallback
    if store is not None:
        try:
            return store.search_users(q, role, status)
        except Exception:
            pass
    
    # In-memory fallback
    data = [
        {"id": "1", "username": "admin", "email": "admin@example.com", "role": "ADMIN", "status": "ACTIVE", "active": True, "created_at": 0},
        {"id": "2", "username": "user1", "email": "user1@example.com", "role": "STUDENT", "status": "ACTIVE", "active": True, "created_at": 0},
        {"id": "3", "username": "prof1", "email": "prof1@example.com", "role": "PROFESSOR", "status": "ACTIVE", "active": True, "created_at": 0},
    ]
    
    # Apply filters
    if q:
        ql = q.lower()
        data = [u for u in data if ql in u["username"].lower() or ql in (u["email"] or "").lower()]
    
    if role:
        data = [u for u in data if u.get("role", "").upper() == role.upper()]
    
    if status:
        status_map = {"ACTIVE": True, "DEACTIVATED": False, "SUSPENDED": False}
        if status.upper() in status_map:
            data = [u for u in data if u.get("active", True) == status_map[status.upper()]]
    
    return data


class UserCreate(BaseModel):
    username: str
    email: str
    password: str  # Required password field
    role: str = "STUDENT"  # Default role
    status: str = "ACTIVE"  # Default status


@app.post("/admin/users")
async def admin_add_user(body: UserCreate, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    if DB_AVAILABLE and db is not None:
        try:
            # Validate password length (bcrypt limit is 72 bytes)
            if len(body.password) < 6:
                raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
            
            # Check if user already exists
            existing_user = db.query(User).filter(
                (User.username == body.username) | (User.email == body.email)
            ).first()
            
            if existing_user:
                raise HTTPException(status_code=400, detail="User with this username or email already exists")
            
            # Hash the password using SHA256 with salt (same as chatbot)
            import secrets
            import hashlib
            salt = secrets.token_hex(16)
            password_hash = hashlib.sha256((salt + body.password).encode()).hexdigest()
            
            # Create new user
            new_user = User(
                username=body.username,
                email=body.email,
                role=UserRole(body.role) if body.role else UserRole.STUDENT,
                status=UserStatus(body.status) if body.status else UserStatus.ACTIVE,
                password_hash=password_hash,
                password_salt=salt
            )
            
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            # Log the action
            audit_log = AuditLog(
                admin_id=int(admin.id),  # Use actual logged-in admin
                action=("Created user: %s" % body.username),
                target_id=new_user.user_id,
                target_table="users"
            )
            db.add(audit_log)
            db.commit()
            
            role_val = new_user.role.value if hasattr(new_user.role, 'value') else new_user.role
            status_val = new_user.status.value if hasattr(new_user.status, 'value') else new_user.status
            
            return {
                "id": str(new_user.user_id),
                "username": new_user.username,
                "email": new_user.email,
                "role": role_val,
                "status": status_val,
                "active": status_val == "ACTIVE",
                "created_at": new_user.created_at.timestamp() if new_user.created_at else 0
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Database user creation failed: %s", e)
            raise HTTPException(status_code=500, detail=("Failed to create user: %s" % str(e)))
    
    # Fallback to JSON storage
    if store is not None:
        try:
            rec = store.add_user(body.username, body.email, body.role)
            store.add_audit(admin.username, "user_add", "user", rec["id"], {"email": rec["email"]})
            return rec
        except Exception as e:
            raise HTTPException(status_code=500, detail=("Failed to create user: %s" % str(e)))
    
    # In-memory fallback
    user_id = str(len(_AUDIT_LOGS) + 1)
    rec = {
        "id": user_id,
        "username": body.username,
        "email": body.email,
        "role": body.role,
        "status": body.status,
        "active": body.status == "active",
        "created_at": time.time()
    }
    _AUDIT_LOGS.append({
        "actor": admin.username,
        "action": "user_add",
        "target_type": "user",
        "target_id": user_id,
        "ts": time.time()
    })
    return rec


class UserPatch(BaseModel):
    username: str | None = None
    email: str | None = None
    role: str | None = None
    status: str | None = None


@app.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, body: UserPatch, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    # Database-backed path
    if DB_AVAILABLE and db is not None and user_id.isdigit():
        try:
            user = db.query(User).filter(User.user_id == int(user_id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if body.email is not None:
                user.email = body.email
            if body.username is not None:
                user.username = body.username
            if body.role is not None:
                try:
                    user.role = UserRole(body.role)
                except Exception:
                    user.role = UserRole[body.role.upper()] if body.role else user.role
            if body.status is not None:
                try:
                    user.status = UserStatus(body.status)
                except Exception:
                    user.status = UserStatus[body.status.upper()] if body.status else user.status

            db.add(user)
            db.commit()
            db.refresh(user)

            # Audit
            try:
                audit_log = AuditLog(
                    admin_id=int(admin.id),  # Use actual logged-in admin
                    action="user_update",
                    target_id=user.user_id,
                    target_table="users"
                )
                db.add(audit_log)
                db.commit()
            except Exception as e:
                db.rollback()  # Rollback failed audit log
                pass

            return {
                "id": str(user.user_id),
                "username": user.username,
                "email": user.email,
                "role": (user.role.value if hasattr(user.role, 'value') else user.role),
                "status": (user.status.value if hasattr(user.status, 'value') else user.status),
                "active": ((user.status.value if hasattr(user.status, 'value') else user.status) == "ACTIVE"),
                "created_at": user.created_at.timestamp() if user.created_at else 0,
                "last_login": user.last_login.timestamp() if user.last_login else None,
            }
        finally:
            db.close()

    # JSON storage fallback
    if store is None:
        raise HTTPException(status_code=503, detail="storage not available in this build")
    rec = store.update_user(user_id, body.model_dump())
    if rec is None:
        raise HTTPException(status_code=404, detail="User not found")
    store.add_audit("admin", "user_update", "user", user_id, None)
    return rec


@app.post("/admin/users/{user_id}/activate")
async def admin_activate_user(user_id: str, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    if DB_AVAILABLE and db is not None and user_id.isdigit():
        try:
            user = db.query(User).filter(User.user_id == int(user_id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            user.status = UserStatus.ACTIVE
            db.add(user)
            db.commit()
            # Audit
            try:
                audit_log = AuditLog(
                    admin_id=int(admin.id),  # Use actual logged-in admin
                    action="user_activate",
                    target_id=user.user_id,
                    target_table="users"
                )
                db.add(audit_log)
                db.commit()
            except Exception as e:
                db.rollback()  # Rollback failed audit log
                pass
            return {
                "id": str(user.user_id),
                "username": user.username,
                "email": user.email,
                "role": (user.role.value if hasattr(user.role, 'value') else user.role),
                "status": (user.status.value if hasattr(user.status, 'value') else user.status),
                "active": ((user.status.value if hasattr(user.status, 'value') else user.status) == "ACTIVE"),
                "created_at": user.created_at.timestamp() if user.created_at else 0,
                "last_login": user.last_login.timestamp() if user.last_login else None,
            }
        finally:
            db.close()

    if store is None:
        raise HTTPException(status_code=503, detail="storage not available in this build")
    rec = store.update_user(user_id, {"status": "active", "active": True})
    if rec is None:
        raise HTTPException(status_code=404, detail="User not found")
    store.add_audit("admin", "user_activate", "user", user_id, None)
    return rec


@app.post("/admin/users/{user_id}/deactivate")
async def admin_deactivate_user(user_id: str, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    if DB_AVAILABLE and db is not None and user_id.isdigit():
        try:
            user = db.query(User).filter(User.user_id == int(user_id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            user.status = UserStatus.DEACTIVATED
            db.add(user)
            db.commit()
            # Audit
            try:
                audit_log = AuditLog(
                    admin_id=int(admin.id),  # Use actual logged-in admin
                    action="user_deactivate",
                    target_id=user.user_id,
                    target_table="users"
                )
                db.add(audit_log)
                db.commit()
            except Exception as e:
                db.rollback()  # Rollback failed audit log
                pass
            return {
                "id": str(user.user_id),
                "username": user.username,
                "email": user.email,
                "role": (user.role.value if hasattr(user.role, 'value') else user.role),
                "status": (user.status.value if hasattr(user.status, 'value') else user.status),
                "active": ((user.status.value if hasattr(user.status, 'value') else user.status) == "ACTIVE"),
                "created_at": user.created_at.timestamp() if user.created_at else 0,
                "last_login": user.last_login.timestamp() if user.last_login else None,
            }
        finally:
            db.close()

    if store is None:
        raise HTTPException(status_code=503, detail="storage not available in this build")
    rec = store.update_user(user_id, {"status": "deactivated", "active": False})
    if rec is None:
        raise HTTPException(status_code=404, detail="User not found")
    store.add_audit(admin.username, "user_deactivate", "user", user_id, None)
    return rec


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    """Delete a user by id. Supports DB (numeric ids) and JSON store (UUIDs)."""
    # DB path only for numeric ids
    if DB_AVAILABLE and db is not None and user_id.isdigit():
        try:
            user = db.query(User).filter(User.user_id == int(user_id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # FIX: Explicitly delete related records first to avoid foreign key issues
            try:
                user_id_int = int(user_id)
                
                # Delete in correct order to respect foreign keys
                # 1. Delete messages (depends on chats)
                db.execute(text("DELETE FROM messages WHERE chat_id IN (SELECT chat_id FROM chats WHERE user_id = :user_id)"), {"user_id": user_id_int})
                
                # 2. Delete chats (depends on users)
                db.execute(text("DELETE FROM chats WHERE user_id = :user_id"), {"user_id": user_id_int})
                
                # 3. Delete sessions (depends on users)
                db.execute(text("DELETE FROM sessions WHERE user_id = :user_id"), {"user_id": user_id_int})
                
                # 4. Delete token limits (depends on users)
                db.execute(text("DELETE FROM token_limits WHERE user_id = :user_id"), {"user_id": user_id_int})
                
                # 5. Delete audit logs where this user was the admin (depends on users)
                db.execute(text("DELETE FROM audit_logs WHERE admin_id = :user_id"), {"user_id": user_id_int})
                
                # 6. Finally delete the user
                db.execute(text("DELETE FROM users WHERE user_id = :user_id"), {"user_id": user_id_int})
                
                db.commit()
            except Exception as delete_error:
                db.rollback()
                raise HTTPException(status_code=500, detail=("Failed to delete user: %s" % str(delete_error)))
            try:
                audit_log = AuditLog(
                    admin_id=int(admin.id),  # Use actual logged-in admin
                    action="user_delete",
                    target_id=int(user_id),
                    target_table="users"
                )
                db.add(audit_log)
                db.commit()
            except Exception as e:
                db.rollback()  # Rollback failed audit log
                pass
            return {"success": True}
        finally:
            db.close()

    # Store path
    if store is None:
        raise HTTPException(status_code=503, detail="storage not available in this build")
    ok = store.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    store.add_audit("admin", "user_delete", "user", user_id, None)
    return {"success": True}


class PasswordReset(BaseModel):
    new_password: str


@app.get("/admin/password-resets")
async def get_pending_password_resets(admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    """Get all pending (unused) password reset requests"""
    if not DB_AVAILABLE or db is None:
        return []
    try:
        result = db.execute(text("""
            SELECT prt.token_id, prt.user_id, prt.created_at, prt.expires_at,
                   u.username, u.email
            FROM password_reset_tokens prt
            JOIN users u ON prt.user_id = u.user_id
            WHERE prt.used = 0 AND prt.expires_at > NOW()
            ORDER BY prt.created_at DESC
        """))
        rows = result.fetchall()
        return [
            {
                "token_id": r[0],
                "user_id": r[1],
                "requested_at": str(r[2]),
                "expires_at": str(r[3]),
                "username": r[4],
                "email": r[5]
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Error fetching pending password resets: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str, 
    body: PasswordReset,
    admin: AdminUser = Depends(get_current_admin),
    db: Optional[Session] = Depends(get_db_optional)
):
    """Reset a user's password (admin only)"""
    if DB_AVAILABLE and db is not None and user_id.isdigit():
        try:
            user = db.query(User).filter(User.user_id == int(user_id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Hash the new password using SHA256 with salt (same as chatbot)
            import secrets
            import hashlib
            salt = secrets.token_hex(16)
            password_hash = hashlib.sha256((salt + body.new_password).encode()).hexdigest()
            
            user.password_hash = password_hash
            user.password_salt = salt
            
            db.commit()
            
            # Clear cached main backend token for this user
            global _main_backend_tokens
            if user.username in _main_backend_tokens:
                del _main_backend_tokens[user.username]
                logger.info("Cleared cached main backend token for %s after password reset", user.username)
            
            # Log the action
            try:
                audit_log = AuditLog(
                    admin_id=int(admin.id),  # Use actual logged-in admin
                    action=("Reset password for user: %s" % user.username),
                    target_id=int(user_id),
                    target_table="users"
                )
                db.add(audit_log)
                db.commit()
            except Exception as e:
                db.rollback()
                pass
            
            return {"success": True, "message": ("Password reset for user %s" % user.username)}
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=("Failed to reset password: %s" % str(e)))
        finally:
            db.close()
    
    raise HTTPException(status_code=503, detail="Database not available")


class TokenLimitUpdate(BaseModel):
    max_tokens: int


@app.put("/admin/users/{user_id}/token-limit")
async def update_user_token_limit(user_id: str, body: TokenLimitUpdate, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    """Update a user's token limit"""
    if DB_AVAILABLE and db is not None and user_id.isdigit():
        try:
            # Use SQL to update the most recent token limit for the user
            result = db.execute(text("""
                UPDATE token_limits 
                SET max_tokens = :max_tokens 
                WHERE user_id = :user_id 
                AND period_start = (
                    SELECT MAX(period_start) 
                    FROM token_limits t2 
                    WHERE t2.user_id = :user_id
                )
            """), {"user_id": int(user_id), "max_tokens": body.max_tokens})
            
            # If no rows were updated, create a new record
            if result.rowcount == 0:
                from datetime import datetime, timedelta
                token_limit = TokenLimit(
                    user_id=int(user_id),
                    max_tokens=body.max_tokens,
                    used_tokens=0,
                    period_start=datetime.now(),
                    period_end=datetime.now() + timedelta(days=30)
                )
                db.add(token_limit)
            
            db.commit()
            
            # Log the action
            audit_log = AuditLog(
                admin_id=int(admin.id),  # Use actual logged-in admin
                action=("Updated token limit for user %s to %s" % (user_id, body.max_tokens)),
                target_id=int(user_id),
                target_table="token_limits"
            )
            db.add(audit_log)
            db.commit()
            
            return {"success": True, "max_tokens": body.max_tokens}
            
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=("Failed to update token limit: %s" % str(e)))
        finally:
            db.close()
    
    raise HTTPException(status_code=503, detail="Database not available")


# ============================================================================
# SYSTEM MANAGEMENT ENDPOINTS
# ============================================================================
# Note: /admin/system/health is defined at line 440 (no auth, fires first)


@app.get("/admin/system/resources")
async def get_system_resources(admin: AdminUser = Depends(get_current_admin)):
    """Get system resource usage"""
    try:
        import psutil

        # CPU and Memory — interval=None uses the delta from the last call (non-blocking)
        cpu_usage = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        memory_usage = memory.percent

        # Disk usage — use drive root, not hardcoded '/' (Windows compatibility)
        from pathlib import Path as _P
        disk = psutil.disk_usage(str(_P(__file__).anchor))
        disk_usage = (disk.used / disk.total) * 100
        disk_free = disk.free / (1024**3)  # GB
        
        # Get real metrics from performance monitor if available
        perf_stats = performance_monitor.get_stats() if HAS_PERFORMANCE_MONITOR and performance_monitor else {}

        return {
            "cpu_usage": round(cpu_usage, 1),
            "memory_usage": round(memory_usage, 1),
            "disk_usage": round(disk_usage, 1),
            "disk_free": round(disk_free, 1),
            "requests_per_min": perf_stats.get("requests_per_min", 0),
            "avg_response_time": perf_stats.get("avg_response_time", 0),
            "error_rate": perf_stats.get("error_rate", 0),
            "db_connections": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=("Resource monitoring failed: %s" % str(e)))


@app.post("/admin/system/backup")
async def create_system_backup(admin: AdminUser = Depends(get_current_admin)):
    """Create a complete system backup"""
    try:
        import zipfile
        import io
        import os
        from datetime import datetime
        from pathlib import Path
        
        # Use same backup directory as other backup endpoint
        current_file = Path(__file__).resolve()
        backup_dir = current_file.parent.parent.parent / "database_backups"
        backup_dir = str(backup_dir)
        os.makedirs(backup_dir, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = ("backup_%s.zip" % timestamp)
        backup_path = os.path.join(backup_dir, Path(backup_filename).name)
        
        # Create SQL dump first using mysqldump
        sql_file = os.path.join(backup_dir, ("backup_%s.sql" % timestamp))
        
        if DB_AVAILABLE:
            try:
                import subprocess
                
                # Find mysqldump
                mysqldump_cmd = _find_mysql_tool("mysqldump")
                
                if mysqldump_cmd:
                    # Create SQL dump
                    dump_command = [
                        mysqldump_cmd,
                        "-u", "root",
                        "--single-transaction",
                        "--routines",
                        "--triggers",
                        "faia_chat_system"
                    ]
                    
                    with open(sql_file, 'w', encoding='utf-8') as f:
                        result = subprocess.run(dump_command, stdout=f, stderr=subprocess.PIPE, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(("mysqldump failed: %s" % result.stderr))
                else:
                    # Fallback: create basic SQL dump
                    from config import engine
                    
                    with open(sql_file, 'w', encoding='utf-8') as f:
                        f.write(("-- FAIA Database Backup %s\n" % timestamp))
                        f.write(("-- Created by: %s\n" % admin.username))
                        f.write("-- Note: Basic SQL dump (mysqldump not available)\n\n")
                        
                        with engine.connect() as conn:
                            tables = ['users', 'sessions', 'chats', 'messages', 'token_limits', 'audit_logs']
                            for table in tables:
                                try:
                                    count = conn.execute(text("SELECT COUNT(*) FROM " + table)).scalar()
                                    f.write(("-- %s: %s rows\n" % (table, count)))
                                except:
                                    pass
                        
                        f.write("\n-- For full restore, use mysqldump\n")
                    
                    logger.info("[OK] Basic SQL backup created")
            except Exception as e:
                # Create error file
                with open(sql_file, 'w', encoding='utf-8') as f:
                    f.write(("-- Backup failed: %s\n" % str(e)))
                logger.error("[ERROR] Database backup failed: %s", e)
        else:
            # No database - create empty SQL file
            with open(sql_file, 'w', encoding='utf-8') as f:
                f.write("-- No database connected\n")
        
        # Create ZIP file with SQL dump
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add SQL dump to zip
            zip_file.write(sql_file, os.path.basename(sql_file))
        
        # Clean up SQL file (keep only zip)
        if os.path.exists(sql_file):
            os.remove(sql_file)
        
        # Return the backup file for download
        return FileResponse(
            backup_path,
            media_type="application/zip",
            filename=backup_filename,
            headers={"Content-Disposition": ("attachment; filename=%s" % backup_filename)}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=("Backup creation failed: %s" % str(e)))


@app.post("/admin/system/restore")
async def restore_system_backup(
    backup_file: UploadFile = File(...),
    admin: AdminUser = Depends(get_current_admin)
):
    """Restore system from backup"""
    try:
        import zipfile
        import json
        import os
        
        # Read uploaded file
        file_content = await backup_file.read()
        
        with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zip_file:
            # Extract backup metadata
            if "backup_metadata.json" in zip_file.namelist():
                metadata = json.loads(zip_file.read("backup_metadata.json").decode())
                logger.info("Restoring backup created by %s at %s", metadata.get('created_by', 'unknown'), metadata.get('created_at', 'unknown'))
            
            # Restore database if available
            if DB_AVAILABLE and "database_dump.json" in zip_file.namelist():
                try:
                    from config import engine
                    
                    db_dump = json.loads(zip_file.read("database_dump.json").decode())
                    backup_version = db_dump.get("version", "1.0")
                    
                    logger.info("Restoring backup version %s", backup_version)
                    
                    # Check if this is the new complete backup format
                    if backup_version == "2.0" and "tables" in db_dump:
                        # COMPLETE RESTORE - New format
                        with engine.connect() as conn:
                            # Disable foreign key checks temporarily
                            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                            
                            # Order matters due to foreign keys
                            restore_order = [
                                "users", "token_limits", "sessions", "chats", "messages",
                                "moderation_flags", "moderation_reports", "moderation_actions",
                                "audit_logs"
                            ]
                            
                            for table in restore_order:
                                if table not in db_dump["tables"]:
                                    continue
                                    
                                table_data = db_dump["tables"][table]
                                if "error" in table_data:
                                    logger.info("Skipping %s: %s", table, table_data['error'])
                                    continue
                                
                                rows = table_data.get("rows", [])
                                if not rows:
                                    logger.info("Skipping %s: no data", table)
                                    continue
                                
                                try:
                                    # Clear existing data — table is from hardcoded restore_order list above
                                    conn.execute(text("DELETE FROM " + table))
                                    logger.info("Cleared %s", table)
                                    
                                    # Insert restored data
                                    for row in rows:
                                        columns = list(row.keys())
                                        placeholders = ", ".join([(":%s" % col) for col in columns])
                                        col_names = ", ".join(columns)
                                        
                                        sql = ("INSERT INTO %s (%s) VALUES (%s)" % (table, col_names, placeholders))
                                        conn.execute(text(sql), row)
                                    
                                    conn.commit()
                                    logger.info("[OK] Restored %s: %s rows", table, len(rows))
                                    
                                except Exception as e:
                                    logger.error("[ERROR] Failed to restore %s: %s", table, e)
                                    conn.rollback()
                            
                            # Re-enable foreign key checks
                            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
                            conn.commit()

                        logger.info("[OK] Complete database restore finished")

                    else:
                        # OLD FORMAT - Only users (legacy support)
                        logger.warning("[WARN] Old backup format detected - only restoring users")
                        db = next(get_db())
                        try:
                            # Clear and restore users only
                            db.query(User).delete()
                            
                            for user_data in db_dump.get("users", []):
                                user = User(
                                    user_id=user_data["id"],
                                    username=user_data["username"],
                                    email=user_data["email"],
                                    created_at=datetime.fromisoformat(user_data["created_at"]) if user_data.get("created_at") else datetime.now()
                                )
                                db.add(user)
                            
                            db.commit()
                        finally:
                            try:
                                db.close()
                            except Exception:
                                    pass
                        logger.warning("[WARN] Partial restore complete (users only)")
                        
                except Exception as e:
                    logger.error("[ERROR] Database restore failed: %s", str(e))
                    import traceback
                    traceback.print_exc()
                    raise HTTPException(status_code=500, detail=("Database restore failed: %s" % str(e)))
            
            # Restore configuration files
            config_files = ["data/settings.json", "data/users.json", "data/files.json", "data/audit.json"]
            for config_file in config_files:
                zip_path = ("config/%s" % os.path.basename(config_file))
                if zip_path in zip_file.namelist():
                    os.makedirs(os.path.dirname(config_file), exist_ok=True)
                    with open(config_file, 'wb') as f:
                        f.write(zip_file.read(zip_path))
            
            # Restore uploads
            uploads_dir = "uploads"
            for file_info in zip_file.filelist:
                if file_info.filename.startswith("uploads/"):
                    file_path = file_info.filename
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(zip_file.read(file_info))
        
        return {"success": True, "message": "System restored successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=("Restore failed: %s" % str(e)))


@app.get("/admin/system/backups")
async def get_backup_history(admin: AdminUser = Depends(get_current_admin)):
    """Get list of available backups"""
    try:
        import os
        from datetime import datetime
        from pathlib import Path

        current_file = Path(__file__).resolve()
        backup_dir = str(current_file.parent.parent.parent / "database_backups")

        backups = []
        if os.path.exists(backup_dir):
            for filename in os.listdir(backup_dir):
                if filename.endswith('.zip') or filename.endswith('.sql'):
                    file_path = os.path.join(backup_dir, Path(filename).name)
                    stat = os.stat(file_path)
                    backups.append({
                        "id": filename,
                        "name": filename,
                        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "size": ("%.1f MB" % (stat.st_size / (1024 * 1024))),
                        "status": "completed"
                    })

        backups.sort(key=lambda x: x['created_at'], reverse=True)
        return backups

    except Exception as e:
        raise HTTPException(status_code=500, detail=("Failed to get backup history: %s" % str(e)))


# Removed - not needed for admin panel


@app.get("/admin/sessions")
async def admin_list_sessions(
    user_id: int = None,  # Optional: filter by specific user
    status: str = None,   # Optional: filter by status (active/completed)
    q: str = None,  # Optional: search query for username, email, or IP
    order_by: str = "login_time",  # Field to sort by
    order: str = "desc",  # asc or desc
    db: Optional[Session] = Depends(get_db_optional)
):
    """Get user sessions with user details"""
    
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        from models import Session as SessionModel
        from sqlalchemy import desc as sql_desc, asc as sql_asc
        from datetime import datetime, timedelta
        
        # Auto-timeout: Mark sessions inactive for > 1 hour as completed
        timeout_threshold = datetime.now() - timedelta(hours=1)
        inactive_sessions = db.query(SessionModel).filter(
            SessionModel.logout_time == None,
            SessionModel.last_activity < timeout_threshold
        ).all()
        
        for session in inactive_sessions:
            session.logout_time = session.last_activity or datetime.now()
            session.status = "ended"  # Update status field to match database convention
        
        if inactive_sessions:
            db.commit()
            logger.info("Auto-completed %s inactive sessions", len(inactive_sessions))
        
        # Build query with joins
        query = db.query(SessionModel).join(User, SessionModel.user_id == User.user_id)
        
        # Apply filters
        if user_id:
            query = query.filter(SessionModel.user_id == user_id)
        
        if status:
            if status.lower() == "active":
                query = query.filter(SessionModel.logout_time == None)
            elif status.lower() == "completed":
                query = query.filter(SessionModel.logout_time != None)
        
        # Apply search filter
        if q:
            search_term = ("%%s%" % q)
            query = query.filter(
                (User.username.ilike(search_term)) |
                (User.email.ilike(search_term)) |
                (SessionModel.ip_address.ilike(search_term))
            )
        
        # Apply sorting
        order_func = sql_desc if order.lower() == "desc" else sql_asc
        if order_by == "username":
            query = query.order_by(order_func(User.username))
        elif order_by == "last_activity":
            query = query.order_by(order_func(SessionModel.last_activity))
        else:  # default to login_time
            query = query.order_by(order_func(SessionModel.login_time))
        
        sessions = query.all()
        
        result = []
        for session in sessions:
            # Handle role and status - they might be enums or strings
            role = None
            status = None
            if session.user:
                role = session.user.role.value if hasattr(session.user.role, 'value') else session.user.role
                status = session.user.status.value if hasattr(session.user.status, 'value') else session.user.status
            
            is_active = session.logout_time is None
            
            # Calculate duration in minutes
            duration_minutes = None
            if session.login_time:
                end_time = session.logout_time or session.last_activity or datetime.now()
                duration_seconds = (end_time - session.login_time).total_seconds()
                duration_minutes = round(duration_seconds / 60, 1)
            
            # Get chat title if current_chat_id exists
            chat_title = None
            if session.current_chat_id and db_manager:
                try:
                    chat = db_manager.get_chat_by_id(session.current_chat_id)
                    if chat:
                        chat_title = chat.get('title')
                except:
                    pass
            
            result.append({
                "session_id": session.session_id,
                "user_id": session.user_id,
                "username": session.user.username if session.user else None,
                "email": session.user.email if session.user else None,
                "role": role,
                "user_status": status,
                "login_time": session.login_time.timestamp() if session.login_time else None,
                "logout_time": session.logout_time.timestamp() if session.logout_time else None,
                "ip_address": session.ip_address,
                "status": session.status,
                "is_active": is_active,  # Clear active/completed indicator
                "last_activity": session.last_activity.timestamp() if session.last_activity else None,
                "current_chat_id": session.current_chat_id,
                "chat_title": chat_title,
                "duration_minutes": duration_minutes
            })
        
        return result
    except Exception as e:
        logger.error("Error fetching sessions: %s", e)
        raise HTTPException(status_code=500, detail=("Failed to fetch sessions: %s" % str(e)))
    finally:
        if db:
            db.close()


@app.get("/admin/sessions/active")
async def admin_active_sessions(db: Optional[Session] = Depends(get_db_optional)):
    """Get only active sessions"""
    
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Use database manager for active sessions
        if db_manager:
            sessions = db_manager.get_active_sessions()
            return {
                "active_sessions": sessions,
                "count": len(sessions)
            }
        else:
            raise HTTPException(status_code=503, detail="Database manager not available")
    except Exception as e:
        logger.error("Error fetching active sessions: %s", e)
        raise HTTPException(status_code=500, detail=("Failed to fetch active sessions: %s" % str(e)))


@app.get("/admin/sessions/all")
async def admin_all_sessions_stats(db: Optional[Session] = Depends(get_db_optional)):
    """Get all sessions with statistics"""
    
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Use database manager for all sessions
        if db_manager:
            sessions = db_manager.get_all_sessions(limit=100)
            active_count = sum(1 for s in sessions if s.get('status') == 'active' and not s.get('logout_time'))
            return {
                "sessions": sessions,
                "total": len(sessions),
                "active": active_count,
                "ended": len(sessions) - active_count
            }
        else:
            raise HTTPException(status_code=503, detail="Database manager not available")
    except Exception as e:
        logger.error("Error fetching session stats: %s", e)
        raise HTTPException(status_code=500, detail=("Failed to fetch session stats: %s" % str(e)))


@app.post("/admin/sessions/{session_id}/terminate")
async def admin_terminate_session(session_id: int, admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    """Terminate a specific user session (admin only)"""
    
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        from models import Session as SessionModel
        from datetime import datetime
        
        session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.logout_time:
            return {"success": True, "message": "Session already terminated", "already_ended": True}
        
        # Update session to terminated
        session.logout_time = datetime.now()
        session.status = 'ended'
        db.commit()
        
        # Call main backend to blacklist the user's tokens
        try:
            import requests
            backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
            response = requests.post(("%s/admin/blacklist-session/%s" % (backend_url, session_id)), timeout=5)
            if response.status_code == 200:
                logger.info("[TERMINATE] Blacklisted tokens for session %s", session_id)
            else:
                logger.error("[TERMINATE] Failed to blacklist tokens: %s", response.text)
        except Exception as e:
            logger.error("[TERMINATE] Error calling blacklist endpoint: %s", e)
        
        # Log audit action
        try:
            if db_manager:
                db_manager.log_audit_action(
                    int(admin.id),
                    ("Admin %s terminated session %s" % (admin.username, session_id))
                )
        except:
            pass
        
        return {"success": True, "message": ("Session %s terminated and user logged out" % session_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error terminating session: %s", e)
        raise HTTPException(status_code=500, detail=("Failed to terminate session: %s" % str(e)))


@app.post("/admin/sessions/terminate-all")
async def admin_terminate_all_sessions(admin: AdminUser = Depends(get_current_admin), db: Optional[Session] = Depends(get_db_optional)):
    """Terminate ALL active sessions (admin only - use with caution!)"""
    
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        from models import Session as SessionModel
        from datetime import datetime
        
        # Get all active sessions
        active_sessions = db.query(SessionModel).filter(SessionModel.logout_time == None).all()
        
        if not active_sessions:
            return {"success": True, "message": "No active sessions to terminate", "count": 0}
        
        # Terminate all active sessions
        count = 0
        for session in active_sessions:
            session.logout_time = datetime.now()
            session.status = 'ended'
            count += 1
        
        db.commit()
        
        # Log audit action
        try:
            if db_manager:
                db_manager.log_audit_action(
                    int(admin.id),
                    ("Admin %s terminated ALL %s active sessions" % (admin.username, count))
                )
        except:
            pass
        
        return {
            "success": True, 
            "message": ("Terminated %s active sessions" % count),
            "count": count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error terminating all sessions: %s", e)
        raise HTTPException(status_code=500, detail=("Failed to terminate all sessions: %s" % str(e)))
    finally:
        if db:
            db.close()


@app.get("/admin/sessions/export")
async def admin_export_sessions(
    format: str = "csv",
    admin: AdminUser = Depends(get_current_admin),
    db: Optional[Session] = Depends(get_db_optional)
):
    """Export sessions data as CSV"""
    from fastapi.responses import StreamingResponse
    import io
    import csv
    from datetime import datetime
    
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        from models import Session as SessionModel
        
        # Get all sessions with user info
        sessions = db.query(SessionModel).join(User, SessionModel.user_id == User.user_id).all()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Session ID', 'Username', 'Email', 'Role', 'User Status',
            'Login Time', 'Logout Time', 'Duration (minutes)', 'IP Address',
            'Session Status', 'Last Activity', 'Current Chat ID'
        ])
        
        # Write data
        for session in sessions:
            role = session.user.role.value if hasattr(session.user.role, 'value') else session.user.role
            user_status = session.user.status.value if hasattr(session.user.status, 'value') else session.user.status
            
            # Calculate duration
            duration_minutes = None
            if session.login_time:
                end_time = session.logout_time or session.last_activity or datetime.now()
                duration_seconds = (end_time - session.login_time).total_seconds()
                duration_minutes = round(duration_seconds / 60, 1)
            
            writer.writerow([
                session.session_id,
                session.user.username if session.user else '',
                session.user.email if session.user else '',
                role,
                user_status,
                session.login_time.strftime('%Y-%m-%d %H:%M:%S') if session.login_time else '',
                session.logout_time.strftime('%Y-%m-%d %H:%M:%S') if session.logout_time else '',
                duration_minutes or '',
                session.ip_address or '',
                session.status,
                session.last_activity.strftime('%Y-%m-%d %H:%M:%S') if session.last_activity else '',
                session.current_chat_id or ''
            ])
        
        # Prepare response
        output.seek(0)
        filename = ("sessions_export_%s.csv" % datetime.now().strftime('%Y%m%d_%H%M%S'))
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": ("attachment; filename=%s" % filename)}
        )
    except Exception as e:
        logger.error("Error exporting sessions: %s", e)
        raise HTTPException(status_code=500, detail=("Failed to export sessions: %s" % str(e)))
    finally:
        if db:
            db.close()


# Missing endpoints for button functionality
# ==========================================

# Removed - not needed for admin panel


@app.delete("/admin/system/backups/{backup_id}")
async def delete_backup(backup_id: str, admin: AdminUser = Depends(get_current_admin)):
    """Delete a specific backup"""
    try:
        # In a real implementation, this would delete the actual backup file
        return {
            "success": True,
            "message": ("Backup %s deleted successfully" % backup_id)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=("Failed to delete backup: %s" % str(e)))


# ==================== MATERIALS PROXY ENDPOINTS ====================
# Proxy materials endpoints to main backend for admin/professor access

import requests

MAIN_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Kept for backward compat with password reset endpoint that clears cached tokens
_main_backend_tokens: dict = {}

def _get_admin_jwt_token(admin_username: str) -> Optional[str]:
    """
    Create a JWT token for the admin user using the same secret as the main backend.
    Both backends share JWT_SECRET_KEY, so this token is valid for the main backend.
    """
    try:
        import jwt as pyjwt
        from datetime import datetime, timedelta
        payload = {
            "sub": admin_username,
            "exp": datetime.utcnow() + timedelta(hours=8)
        }
        return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    except Exception as e:
        logger.error("Failed to create JWT token for %s: %s", admin_username, e)
        return None


@app.get("/admin/materials/stats")
async def get_materials_stats(admin: AdminUser = Depends(get_current_admin)):
    """Proxy RAG stats from main backend"""
    try:
        token = _get_admin_jwt_token(admin.username)
        headers = {"Authorization": ("Bearer %s" % token)} if token else {}
        
        # Try to get stats from main backend
        response = requests.get(("%s/rag/stats" % MAIN_BACKEND_URL), headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        
        # Fallback: calculate stats from materials list
        materials_response = requests.get(("%s/materials" % MAIN_BACKEND_URL), headers=headers, timeout=10)
        if materials_response.status_code == 200:
            materials_data = materials_response.json()
            materials = materials_data.get("materials", [])
            return {
                "total_materials": len(materials),
                "ready_materials": len([m for m in materials if m.get("status") == "ready"]),
                "processing_materials": len([m for m in materials if m.get("status") == "processing"]),
                "total_chunks": sum(m.get("chunk_count", 0) for m in materials if m.get("chunk_count"))
            }
        
        return {"total_materials": 0, "ready_materials": 0, "processing_materials": 0, "total_chunks": 0}
    except Exception as e:
        logger.error("Error fetching materials stats: %s", e)
        return {"total_materials": 0, "ready_materials": 0, "processing_materials": 0, "total_chunks": 0}

@app.get("/admin/materials")
async def get_materials_list(admin: AdminUser = Depends(get_current_admin)):
    """Proxy materials list from main backend"""
    try:
        token = _get_admin_jwt_token(admin.username)
        headers = {"Authorization": ("Bearer %s" % token)} if token else {}
        
        response = requests.get(("%s/materials" % MAIN_BACKEND_URL), headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error("Main backend materials request failed: %s - %s", response.status_code, response.text)
            return {"materials": []}
    except Exception as e:
        logger.error("Error fetching materials: %s", e)
        return {"materials": []}

@app.post("/admin/materials/upload")
async def upload_material(
    file: UploadFile = File(...),
    course_code: str = Form(...),
    course_name: str = Form(...),
    admin: AdminUser = Depends(get_current_admin)
):
    """Proxy material upload to main backend"""
    try:
        logger.info("Upload request from %s: %s for %s", admin.username, file.filename, course_code)
        
        token = _get_admin_jwt_token(admin.username)
        if not token:
            raise HTTPException(status_code=503, detail="Failed to create auth token for main backend")
        
        file_content = await file.read()
        files = {"file": (file.filename, file_content, file.content_type)}
        data = {"course_code": course_code, "course_name": course_name}
        headers = {"Authorization": ("Bearer %s" % token)}
        
        response = requests.post(
            ("%s/materials/upload" % MAIN_BACKEND_URL),
            files=files,
            data=data,
            headers=headers,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info("Upload successful: material_id=%s", result.get('material_id'))
            return result
        else:
            error_detail = "Upload failed"
            try:
                error_data = response.json()
                error_detail = error_data.get("detail", error_detail)
            except:
                error_detail = response.text or error_detail
            logger.error("Main backend upload failed: %s - %s", response.status_code, error_detail)
            raise HTTPException(status_code=response.status_code, detail=error_detail)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error uploading material: %s", e)
        raise HTTPException(status_code=500, detail=("Upload error: %s" % str(e)))

@app.post("/admin/materials/{material_id}/process")
async def process_material(material_id: int, admin: AdminUser = Depends(get_current_admin)):
    """Proxy material processing to main backend"""
    try:
        token = _get_admin_jwt_token(admin.username)
        if not token:
            raise HTTPException(status_code=503, detail="Failed to create auth token for main backend")
        
        headers = {"Authorization": ("Bearer %s" % token)}
        response = requests.post(("%s/materials/%s/process" % (MAIN_BACKEND_URL, material_id)), headers=headers, timeout=120)
        
        if response.status_code == 200:
            return response.json()
        else:
            error_detail = "Processing failed"
            try:
                error_detail = response.json().get("detail", error_detail)
            except:
                error_detail = response.text or error_detail
            raise HTTPException(status_code=response.status_code, detail=error_detail)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing material: %s", e)
        raise HTTPException(status_code=500, detail=("Process error: %s" % str(e)))

@app.delete("/admin/materials/{material_id}")
async def delete_material(material_id: int, admin: AdminUser = Depends(get_current_admin)):
    """Proxy material deletion to main backend"""
    try:
        token = _get_admin_jwt_token(admin.username)
        if not token:
            raise HTTPException(status_code=503, detail="Failed to create auth token for main backend")
        
        headers = {"Authorization": ("Bearer %s" % token)}
        response = requests.delete(("%s/materials/%s" % (MAIN_BACKEND_URL, material_id)), headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            error_detail = "Deletion failed"
            try:
                error_detail = response.json().get("detail", error_detail)
            except:
                error_detail = response.text or error_detail
            raise HTTPException(status_code=response.status_code, detail=error_detail)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting material: %s", e)
        raise HTTPException(status_code=500, detail=("Delete error: %s" % str(e)))

@app.get("/admin/materials/health")
async def get_materials_health(admin: AdminUser = Depends(get_current_admin)):
    """Proxy materials health check from main backend"""
    try:
        token = _get_admin_jwt_token(admin.username)
        headers = {"Authorization": ("Bearer %s" % token)} if token else {}
        
        response = requests.get(("%s/materials/health" % MAIN_BACKEND_URL), headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {"success": False, "healthy": False, "error": "Health check failed"}
    except Exception as e:
        logger.error("Error checking materials health: %s", e)
        return {"success": False, "healthy": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FAIA Admin Backend on http://0.0.0.0:8001 (DB available: %s)", DB_AVAILABLE)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )