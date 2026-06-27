from fastapi import FastAPI, HTTPException, Depends, status, Form, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import jwt
import time
import secrets
import html
import re
import os
import asyncio
import hashlib
import torch
from dotenv import load_dotenv

# Load environment variables first — must be before any env var usage
load_dotenv()

# Fail fast if JWT secret is missing — better to crash here than at first request
import os as _os
if not _os.getenv("JWT_SECRET_KEY"):
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Set it in your .env file. See .env.example for details."
    )

import logging
from datetime import datetime
from pathlib import Path
import shutil
import mimetypes
import base64
from PIL import Image
from io import BytesIO
from PyPDF2 import PdfReader
import json
import sys
sys.path.append(str(Path(__file__).parent.parent))

# Logger must be defined before any try/except blocks that use it
logger = logging.getLogger(__name__)

# Import database integration
try:
    from database.database_integration import db_manager
except ImportError:
    logger.warning("Database integration not found - using stub")
    class DBManagerStub:
        def __getattr__(self, name): return lambda *args, **kwargs: None
    db_manager = DBManagerStub()

# Import RAG service (optional for smoke testing)
try:
    rag_enabled = os.getenv("ENABLE_RAG", "false").lower() == "true"
    if rag_enabled:
        from services.rag_service import rag_service
    else:
        raise RuntimeError("RAG disabled by configuration")
except BaseException as e:
    logger.warning("RAG service unavailable - using stub: %s", e)
    class RAGServiceStub:
        def search(self, *args, **kwargs): return []
        def build_rag_context(self, *args, **kwargs): return ""
        def get_stats(self): return {}
    rag_service = RAGServiceStub()

# ==================== CONVERSATION MEMORY SYSTEM ====================
# In-memory storage for guest sessions (cookie-based)
guest_sessions = {}  # {guest_id: {"history": [...], "last_activity": timestamp}}

# ==================== TEMPORARY FILE MEMORY SYSTEM (ChatGPT-style) ====================
# Store file content in memory temporarily (expires after 1 minute or session end)
temporary_file_memory = {}  # {chat_id: {"filename": str, "content": str, "expires_at": timestamp}}

def set_temporary_file_memory(chat_id: int, file_data: dict):
    """Store file content in temporary memory with expiration"""
    temporary_file_memory[chat_id] = file_data
    logger.info("Stored file in temporary memory for chat %s: %s (expires at %s)", chat_id, file_data.get('filename'), file_data.get('expires_at'))

def get_temporary_file_memory(chat_id: int) -> Optional[dict]:
    """Get file content from temporary memory if not expired"""
    if chat_id not in temporary_file_memory:
        return None
    
    file_data = temporary_file_memory[chat_id]
    current_time = time.time()
    
    # Check if expired
    if current_time > file_data.get("expires_at", 0):
        # Expired - remove from memory
        del temporary_file_memory[chat_id]
        logger.info("File memory expired and removed for chat %s: %s", chat_id, file_data.get('filename'))
        return None
    
    return file_data

def clear_temporary_file_memory(chat_id: int):
    """Clear file memory for a specific chat"""
    if chat_id in temporary_file_memory:
        file_data = temporary_file_memory.pop(chat_id)
        logger.info("Cleared file memory for chat %s: %s", chat_id, file_data.get('filename'))

def cleanup_expired_file_memory():
    """Clean up expired file memories"""
    current_time = time.time()
    expired_chats = []
    
    for chat_id, file_data in temporary_file_memory.items():
        if current_time > file_data.get("expires_at", 0):
            expired_chats.append(chat_id)
    
    for chat_id in expired_chats:
        file_data = temporary_file_memory.pop(chat_id)
        logger.info("Cleaned up expired file memory for chat %s: %s", chat_id, file_data.get('filename'))
    
    return len(expired_chats)

# ==================== END TEMPORARY FILE MEMORY SYSTEM ====================

# Redis not used — in-memory fallback only
redis_client = None
REDIS_AVAILABLE = False
guest_token_usage = {}  # In-memory dict: {guest_id: {"used": int, "window_start": float}}

# Configuration
GUEST_MAX_HISTORY_TURNS = 6
STUDENT_MAX_HISTORY_TURNS = 15
GUEST_TTL_MINUTES = 5  # Guest session expires after 5 min of inactivity

# Concurrency control for model processing
MAX_CONCURRENT_REQUESTS = 3  # Allow up to 3 concurrent chat requests
chat_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
GUEST_TOKEN_TTL_HOURS = 8  # Guest token usage expires after 8 hours
# Guest token limit is read from database via db_manager.get_guest_token_limit()

def cleanup_expired_guests():
    """Remove expired guest sessions"""
    current_time = time.time()
    expired = [
        guest_id for guest_id, data in guest_sessions.items()
        if current_time - data["last_activity"] > (GUEST_TTL_MINUTES * 60)
    ]
    for guest_id in expired:
        del guest_sessions[guest_id]
    if expired:
        logger.info("Cleaned up %s expired guest sessions", len(expired))

def check_guest_token_limit(guest_id: str, estimated_tokens: int) -> dict:
    """Check if guest has enough tokens (8-hour window, survives restarts via Redis)"""
    guest_limit = db_manager.get_guest_token_limit()
    window_seconds = GUEST_TOKEN_TTL_HOURS * 3600

    if REDIS_AVAILABLE and redis_client:
        redis_key = f"guest:{guest_id}:tokens"
        used_tokens = redis_client.get(redis_key)
        used_tokens = int(used_tokens) if used_tokens else 0
        ttl = redis_client.ttl(redis_key)
        time_remaining = ttl if ttl > 0 else 0
    else:
        # In-memory fallback with time window
        current_time = time.time()
        entry = guest_token_usage.get(guest_id)
        if entry:
            elapsed = current_time - entry["window_start"]
            if elapsed >= window_seconds:
                # Window expired - reset
                guest_token_usage[guest_id] = {"used": 0, "window_start": current_time}
                used_tokens = 0
                time_remaining = 0
            else:
                used_tokens = entry["used"]
                time_remaining = int(window_seconds - elapsed)
        else:
            used_tokens = 0
            time_remaining = 0

    new_usage = used_tokens + estimated_tokens
    can_use = new_usage <= guest_limit

    return {
        "can_use": can_use,
        "used_today": used_tokens,
        "remaining_tokens": max(0, guest_limit - used_tokens),
        "limit": guest_limit,
        "estimated_tokens": estimated_tokens,
        "time_remaining_seconds": time_remaining
    }

def update_guest_token_usage(guest_id: str, tokens_used: int):
    """Update guest token usage (persists in Redis with 8-hour TTL)"""
    if REDIS_AVAILABLE and redis_client:
        redis_key = f"guest:{guest_id}:tokens"
        new_usage = redis_client.incr(redis_key, tokens_used)
        if redis_client.ttl(redis_key) == -1:
            redis_client.expire(redis_key, GUEST_TOKEN_TTL_HOURS * 3600)
        logger.info("Guest %s used %s tokens. Total: %s (Redis, 8h TTL)", guest_id, tokens_used, new_usage)
    else:
        # In-memory fallback with time window
        current_time = time.time()
        entry = guest_token_usage.get(guest_id)
        if entry:
            entry["used"] += tokens_used
        else:
            guest_token_usage[guest_id] = {"used": tokens_used, "window_start": current_time}
        logger.info("Guest %s used %s tokens. Total: %s (in-memory)", guest_id, tokens_used, guest_token_usage[guest_id]['used'])

def build_chatml_history(session_id: str, is_guest: bool, chat_id: int = None) -> List[dict]:
    """Build ChatML message history from storage"""
    if is_guest:
        # Guest: load from in-memory dict
        cleanup_expired_guests()
        if session_id in guest_sessions:
            return guest_sessions[session_id]["history"]
        return []
    else:
        # Student: load from database messages table
        if not chat_id:
            return []
        
        try:
            # Get messages from database for this chat
            messages = db_manager.get_chat_messages(chat_id)
            
            # Convert to ChatML format
            history = []
            for msg in messages:
                sender = msg["sender"].upper()
                if sender == "USER":
                    role = "user"
                elif sender == "SYSTEM":
                    role = "system"
                else:
                    role = "assistant"
                history.append({
                    "role": role,
                    "content": msg["content"]
                })
            
            logger.info("Loaded {len(history)} messages from database for chat_id %s", chat_id)
            # Only pass the last N turns to Qwen - keeps responses fast without deleting history
            return history[-(STUDENT_MAX_HISTORY_TURNS * 2):]
        except Exception as e:
            logger.error("Error loading chat history from database: %s", e)
            return []

def save_turn(session_id: str, user_msg: str, assistant_msg: str, is_guest: bool, chat_id: int = None):
    """Save a conversation turn to storage"""
    # Determine max history based on user type
    max_turns = GUEST_MAX_HISTORY_TURNS if is_guest else STUDENT_MAX_HISTORY_TURNS
    
    if is_guest:
        # Guest: save to in-memory dict
        new_turns = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg}
        ]
        
        if session_id not in guest_sessions:
            guest_sessions[session_id] = {"history": [], "last_activity": time.time()}
        guest_sessions[session_id]["history"].extend(new_turns)
        guest_sessions[session_id]["last_activity"] = time.time()
        
        # Trim to max turns (keep most recent)
        if len(guest_sessions[session_id]["history"]) > max_turns * 2:
            guest_sessions[session_id]["history"] = guest_sessions[session_id]["history"][-(max_turns * 2):]
    else:
        # Student: save to database messages table
        if not chat_id:
            logger.warning("Cannot save turn: chat_id is None for registered user")
            return
        
        try:
            # Save user message
            db_manager.save_message(chat_id, "user", user_msg, len(user_msg) // 4)
            # Save assistant message
            db_manager.save_message(chat_id, "ai", assistant_msg, len(assistant_msg) // 4)
            
            logger.info("Saved conversation turn to database for chat_id %s", chat_id)
            # No DB trim - all messages kept for display history
            # AI context is limited by slicing in build_chatml_history()
        except Exception as e:
            logger.error("Error saving chat history to database: %s", e)
# ==================== END CONVERSATION MEMORY SYSTEM ====================

# ==================== FILE EXTRACTION HELPER ====================
def _extract_text_for_context(file_info: dict) -> str:
    """Extract text content from uploaded file"""
    try:
        file_path = file_info.get("filepath")
        mime_type = file_info.get("mime_type")
        if not file_path or not os.path.exists(file_path):
            return ""
        with open(file_path, "rb") as f:
            content = f.read()

        # Simple handlers for different file types
        if mime_type in ['text/plain', 'text/markdown']:
            try:
                return content.decode('utf-8', errors='ignore')
            except Exception:
                return ""
        elif mime_type == 'application/pdf':
            # Try PyPDF2 first
            try:
                pdf_reader = PdfReader(BytesIO(content))
                text_content = ""
                for page in pdf_reader.pages[:12]:  # limit pages for speed
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_content += "\n" + page_text
                    except Exception:
                        continue
                if text_content.strip():
                    return text_content
            except Exception as e:
                logger.warning("PyPDF2 read error: %s", e)
            # Fallback to PyMuPDF for scanned/complex PDFs
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=content, filetype="pdf")
                text_content = ""
                for i, page in enumerate(doc):
                    if i >= 12:
                        break
                    try:
                        page_text = page.get_text()
                        if page_text:
                            text_content += "\n" + page_text
                    except Exception:
                        continue
                doc.close()
                return text_content
            except Exception as e2:
                logger.warning("PyMuPDF read error: %s", e2)
                return ""
        elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
            # Handle Word documents (.docx and .doc)
            try:
                # Try python-docx for .docx files
                if mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                    try:
                        from docx import Document
                        doc = Document(BytesIO(content))
                        text_content = ""
                        for paragraph in doc.paragraphs:
                            text_content += paragraph.text + "\n"
                        return text_content.strip()
                    except ImportError:
                        logger.warning("python-docx not available, trying alternative extraction")
                        # Fallback: try to extract text using zipfile (docx is a zip)
                        import zipfile
                        import xml.etree.ElementTree as ET
                        try:
                            with zipfile.ZipFile(BytesIO(content)) as docx_zip:
                                # Read the main document XML
                                doc_xml = docx_zip.read('word/document.xml')
                                root = ET.fromstring(doc_xml)
                                # Extract text from all text nodes
                                text_content = ""
                                for elem in root.iter():
                                    if elem.text:
                                        text_content += elem.text + " "
                                return text_content.strip()
                        except Exception as e:
                            logger.warning("Fallback docx extraction failed: %s", e)
                            return f"[Word document uploaded - install python-docx for full text extraction]"
                else:
                    # For .doc files, we need python-docx2txt or similar
                    try:
                        import docx2txt
                        return docx2txt.process(BytesIO(content))
                    except ImportError:
                        logger.warning("docx2txt not available for .doc files")
                        return f"[Word .doc document uploaded - install docx2txt for text extraction]"
            except Exception as e:
                logger.warning("Word document extraction error: %s", e)
                return f"[Word document uploaded - text extraction failed: {str(e)}]"
        elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
            # Handle Excel files (.xls and .xlsx)
            try:
                import pandas as pd
                # Read Excel file and convert to text
                df = pd.read_excel(BytesIO(content), sheet_name=None)  # Read all sheets
                text_content = ""
                for sheet_name, sheet_df in df.items():
                    text_content += f"Sheet: {sheet_name}\n"
                    text_content += sheet_df.to_string(index=False) + "\n\n"
                return text_content.strip()
            except ImportError:
                logger.warning("pandas not available for Excel extraction")
                return f"[Excel document uploaded - install pandas for text extraction]"
            except Exception as e:
                logger.warning("Excel extraction error: %s", e)
                return f"[Excel document uploaded - text extraction failed: {str(e)}]"
        else:
            # For other types, return placeholder
            return f"[File type {mime_type} - content extraction not supported]"
    except Exception as e:
        logger.error("Context extraction error: %s", e)
        return ""
# ==================== END FILE EXTRACTION HELPER ====================

# Import cache manager
try:
    from services.cache_manager import cache_manager
except ImportError:
    logger.warning("Cache manager not found - using stub")
    class CacheManagerStub:
        def get_chat_response(self, *args, **kwargs): return None
        def set_chat_response(self, *args, **kwargs): pass
        def get_stats(self): return {}
    cache_manager = CacheManagerStub()

# ==================== QWEN BRAIN - EMBEDDED ====================
import chromadb

# Qwen model path — must be set in .env (see .env.example)
MODEL_PATH = os.getenv("QWEN_MODEL_PATH")
if not MODEL_PATH:
    logger.warning("QWEN_MODEL_PATH not set — model features will be unavailable until configured")
CHROMA_PATH = "./chroma_db"
CHROMA_COLL = "course_materials"

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
chroma_coll = chroma_client.get_or_create_collection(CHROMA_COLL)

def generate_qwen_response(prompt: str, use_rag: bool = False, course_code: str = None, conversation_history: List[dict] = None) -> str:
    """Placeholder - overwritten by import from model_service below"""
    raise RuntimeError("model_service import did not complete")

# Stub functions for compatibility (removed dependencies)
class ErrorMonitorStub:
    def get_error_summary(self, hours=24): return {"errors": []}
    def resolve_error(self, error_id, notes=None): return True

error_monitor = ErrorMonitorStub()

# Monitoring functions moved to earlier in file

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8080").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from model_service import model_service, generate_qwen_response

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting FAIA Backend with Qwen Brain...")
    
    try:
        # Load Qwen model using centralized model service
        if model_service.is_model_loaded():
            logger.info("Qwen model loaded and ready")
        else:
            # Try to load the model
            model_service._load_model()
            if model_service.is_model_loaded():
                logger.info("Qwen model loaded and ready")
            else:
                logger.error("Failed to load Qwen model")
        
        logger.info("Backend initialized successfully")
        
    except Exception as e:
        logger.error("Critical startup failure: %s", e)
        raise

# Secret key for JWT encoding/decoding — must match admin backend
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Set it in your .env file. See .env.example for details."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 28800  # 8 hours

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# In-memory token blacklist for logout
# NOTE: This is lost on restart and won't work across multiple workers.
# For production with multiple workers, move to Redis or database.
token_blacklist = set()

# Database-backed user management (replacing in-memory storage)

# ==================== HEALTH CHECK & MONITORING ENDPOINTS ====================

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        with monitor_operation("backend", "health_check", "low", "system"):
            # Get system metrics
            import psutil
            
            # Check model status
            model_info = model_service.get_model_info()
            
            # Check database connection
            db_healthy = True
            try:
                db_manager.get_user_by_username("health_check_test")
            except Exception as e:
                db_healthy = False
                log_error("high", "database", "backend", "db_health_check_failed",
                         f"Database health check failed: {str(e)}", e)
            
            # Check cache status
            cache_stats = cache_manager.get_stats()
            
            # System metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            health_data = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "FAIA Backend",
                "version": "1.0.0",
                "model_service": {
                    "model_loaded": model_info.get("model_loaded", False),
                    "model_path": model_info.get("model_path"),
                    "loading_error": model_info.get("loading_error")
                },
                "database": {
                    "connected": db_healthy,
                    "status": "healthy" if db_healthy else "error"
                },
                "cache": {
                    "status": "healthy",
                    "stats": cache_stats
                },
                "system_metrics": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_used_gb": round(memory.used / (1024**3), 2),
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_percent": disk.percent,
                    "disk_free_gb": round(disk.free / (1024**3), 2)
                }
            }
            
            # Determine overall health status
            if not db_healthy:
                health_data["status"] = "critical"
            elif not model_info.get("model_loaded", False):
                health_data["status"] = "warning"
            elif cpu_percent > 90 or memory.percent > 90:
                health_data["status"] = "critical"
            elif cpu_percent > 80 or memory.percent > 80:
                health_data["status"] = "warning"
            
            return health_data
            
    except Exception as e:
        log_error("critical", "system", "backend", "health_check_failed", 
                         f"Health check endpoint failed: {str(e)}", e)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": "Health check failed",
            "details": str(e)
        }

@app.get("/admin/system/health")
async def admin_system_health():
    """Admin endpoint for comprehensive system health"""
    try:
        with monitor_operation("backend", "admin_health_check"):
            # Get comprehensive health data
            health_data = await health_check()
            
            # Add error monitoring data
            error_summary = error_monitor.get_error_summary(hours=24)
            health_data["error_monitoring"] = error_summary
            
            return health_data
            
    except Exception as e:
        logger.critical("Admin health check failed: %s", e)
        return {
            "status": "error",
            "error": "Admin health check failed",
            "details": str(e)
        }

@app.get("/admin/system/errors")
async def get_error_summary(hours: int = 24):
    """Get error summary for admin panel"""
    try:
        with monitor_operation("backend", "get_error_summary"):
            return error_monitor.get_error_summary(hours)
    except Exception as e:
        log_error("high", "api", "backend", "error_summary_failed",
                 f"Failed to get error summary: {str(e)}", e)
        return {"error": "Failed to get error summary", "details": str(e)}

@app.post("/admin/system/errors/{error_id}/resolve")
async def resolve_error(error_id: str, resolution_notes: str = None):
    """Mark an error as resolved"""
    try:
        with monitor_operation("backend", "resolve_error"):
            success = error_monitor.resolve_error(error_id, resolution_notes)
            if success:
                return {"success": True, "message": "Error marked as resolved"}
            else:
                return {"success": False, "message": "Error not found"}
    except Exception as e:
        log_error("medium", "api", "backend", "resolve_error_failed",
                 f"Failed to resolve error {error_id}: {str(e)}", e)
        return {"error": "Failed to resolve error", "details": str(e)}


# Directory for uploaded files
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory file metadata storage: session_id -> list of files
file_db = {}

# Add these after other global variables
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB for larger study documents
ALLOWED_MIME_TYPES = {
    # Documents
    'application/pdf': '.pdf',  # PDF files
    'application/msword': '.doc',  # Word documents
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',  # Modern Word
    'application/vnd.ms-excel': '.xls',  # Excel files
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',  # Modern Excel
    'text/plain': '.txt',  # Text files
    'text/markdown': '.md',  # Markdown files
    # Images
    'image/jpeg': '.jpg',
    'image/png': '.png',
    # Audio
    'audio/mpeg': '.mp3',
    'audio/wav': '.wav',
    'audio/ogg': '.ogg'
}

# Global model references - managed by centralized model_service
qwen_model = None
qwen_tokenizer = None

# update_global_model_references removed - unused

# Security functions
def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS and injection attacks"""
    if not text:
        return ""
    # HTML escape
    text = html.escape(text)
    # Remove potential script tags
    text = re.sub(r'<script.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # Remove potential javascript: protocols
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    return text.strip()

# Basic validation functions
def validate_username(username: str) -> tuple[bool, str]:
    """Validate username format"""
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters long"
    if len(username) > 50:
        return False, "Username must be less than 50 characters"
    if not username.replace('_', '').replace('-', '').isalnum():
        return False, "Username can only contain letters, numbers, hyphens, and underscores"
    return True, "Valid username"

def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password strength"""
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters long"
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    return True, "Valid password"

def validate_email(email: str) -> tuple[bool, str]:
    """Validate email format"""
    if not email:
        return False, "Email is required"
    if '@' not in email or '.' not in email:
        return False, "Invalid email format"
    if len(email) > 254:
        return False, "Email is too long"
    return True, "Valid email"

# Simple monitoring context manager
class monitor_operation:
    """Simple context manager for operation monitoring"""
    def __init__(self, service: str, operation: str, priority: str, category: str):
        self.service = service
        self.operation = operation
        self.priority = priority
        self.category = category
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logger.error("Operation failed: {self.service}.{self.operation} - %s", exc_val)
        return False

# Simple error logging function
def log_error(level: str, category: str, service: str, operation: str, message: str):
    """Simple error logging function"""
    logger.info("[{level.upper()}] {category}.{service}.{operation}: %s", message)

def enforce_faia_identity(response: str) -> str:
    """Ensure FAIA maintains its identity and doesn't reveal underlying model"""
    if not response:
        return response
    
    # Common identity-breaking patterns
    identity_patterns = [
        (r'\bQwen\b', 'FAIA'),
        (r'\bAlibaba Cloud\b', 'the FAIA development team'),
        (r'\bAlibaba\b', 'the FAIA development team'),
        (r'I am Qwen', 'I am FAIA'),
        (r'My name is Qwen', 'My name is FAIA'),
        (r'developed by Alibaba', 'developed by the FAIA team'),
        (r'created by Alibaba', 'created by the FAIA team'),
        (r'I\'m Qwen', 'I\'m FAIA'),
    ]
    
    # Apply replacements
    corrected_response = response
    for pattern, replacement in identity_patterns:
        corrected_response = re.sub(pattern, replacement, corrected_response, flags=re.IGNORECASE)
    
    return corrected_response

# PHI-2 model loading is now handled by centralized model_service
# This eliminates redundant model loading and reduces memory usage
logger.info("Model service initialized. Info: %s", model_service.get_model_info())

# Update timeout constants
QWEN_TIMEOUT = 30  # seconds

class User(BaseModel):
    username: str
    password: str  # Stored as salted hash
    email: Optional[str] = None

class UserInDB(User):
    salt: str
    default_model: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None
    status: Optional[str] = None

    model_config = {"extra": "allow"}


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    session_id: Optional[int] = None

class ResetResponse(BaseModel):
    success: bool
    message: str
    chats_deleted: Optional[int] = 0
    tokens_recovered: Optional[int] = 0
    tokens_returned: Optional[int] = 0
    sessions_ended: Optional[int] = 0
    files_cleared: Optional[int] = 0

class PromptRequest(BaseModel):
    prompt: str
    model: Optional[str] = None  # Only "qwen" supported
    session_id: Optional[str] = None
    chat_id: Optional[str] = None  # For continuing existing conversations
    file_context: Optional[dict] = None
    response_control: Optional[dict] = None
    # RAG fields
    use_rag: Optional[bool] = False  # Enable RAG mode
    course_code: Optional[str] = None  # Filter by course
    rag_top_k: Optional[int] = 5  # Number of chunks to retrieve
    guest_new_page_load: Optional[bool] = False  # True on first message after page load/refresh - clears guest memory

class LogoutRequest(BaseModel):
    session_id: Optional[int] = None

def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()

def verify_password(password: str, salt: str, hashed: str) -> bool:
    return hash_password(password, salt) == hashed

def create_access_token(username: str, expires_in: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    payload = {
        "sub": username,
        "exp": int(time.time()) + expires_in
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if token in token_blacklist:
            raise HTTPException(status_code=401, detail="Token has been revoked")
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        logger.warning("Expired token attempt")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired - please login again")
    except jwt.InvalidTokenError:
        logger.warning("Invalid token attempt")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    # Token validation
    
    # NO GUEST ACCESS - Require authentication
    if not token:
        # Return guest user (will be blocked at endpoint level)
        return UserInDB(username="guest", password="", salt="", email=None, default_model="qwen")
    
    # Handle regular user authentication
    try:
        username = decode_access_token(token)
        if not username:
            # No username in token, return guest user (will be blocked at endpoint level)
            return UserInDB(username="guest", password="", salt="", email=None, default_model="qwen")
            
        # Get user from database
        user_data = db_manager.get_user_by_username(username)
        if not user_data:
            # User not found in database
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        
        # Update last login
        db_manager.update_last_login(user_data["user_id"])
        
        # Convert to UserInDB format
        user = UserInDB(
            username=user_data["username"],
            password="",  # Don't expose password hash
            salt="",
            email=user_data["email"],
            default_model="qwen",
            user_id=user_data["user_id"],
            role=user_data["role"],
            status=user_data["status"]
        )
        
        return user
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")


def classify_user_role(email: str, username: str) -> str:
    """
    Classify user role based on email domain and username
    
    Rules:
    - ADMIN: username contains 'admin' OR email ends with @admin.faia.edu
    - PROFESSOR: email ends with @prof.faia.edu OR @faculty.faia.edu
    - STUDENT: default for everyone else
    """
    email_lower = email.lower()
    username_lower = username.lower()
    
    # Check for admin
    if 'admin' in username_lower or email_lower.endswith('@admin.faia.edu'):
        return 'ADMIN'
    
    # Check for professor
    if email_lower.endswith('@prof.faia.edu') or email_lower.endswith('@faculty.faia.edu'):
        return 'PROFESSOR'
    
    # Default to student
    return 'STUDENT'


@app.post("/register", response_model=Token)
async def register(username: str = Form(...), password: str = Form(...), email: Optional[str] = Form(None)):
    # Sanitize inputs
    username = sanitize_input(username)
    
    # Log registration attempt
    log_error("low", "authentication", "backend", "registration_attempt",
             f"Registration attempt for username: {username}")
    
    try:
        with monitor_operation("backend", "user_registration", "medium", "authentication"):
            password = sanitize_input(password)
            email = sanitize_input(email) if email else None
            
            # Validate inputs
            username_valid, username_msg = validate_username(username)
            if not username_valid:
                raise HTTPException(status_code=400, detail=username_msg)
            
            password_valid, password_msg = validate_password_strength(password)
            if not password_valid:
                raise HTTPException(status_code=400, detail=password_msg)
            
            if email:
                email_valid, email_msg = validate_email(email)
                if not email_valid:
                    raise HTTPException(status_code=400, detail=email_msg)
            
            # Check if user already exists in database
            existing_user = db_manager.get_user_by_username(username)
            if existing_user:
                raise HTTPException(status_code=400, detail="Username already exists")
            
            # Create user in database
            salt = secrets.token_hex(16)  # 32 character salt
            hashed_password = hash_password(password, salt)
            
            # Automatically classify user role based on email domain (users cannot choose their role)
            final_email = email or f"{username}@faia.edu"
            user_role = classify_user_role(final_email, username)
            
            user_id = db_manager.create_user(username, final_email, hashed_password, salt, user_role)
            if not user_id:
                raise HTTPException(status_code=500, detail="Failed to create user")
            
            # Create token limit for new user
            db_manager.create_token_limit(user_id)
            
            # FIX: Create session for new user (same as login)
            session_id = db_manager.create_session(user_id, None)
            
            # Log audit action
            db_manager.log_audit_action(user_id, "User registered: %s as %s" % (username, user_role))
            
            # Create a welcome chat for the new user
            try:
                from datetime import datetime
                welcome_title = f"Welcome to FAIA! - {datetime.now().strftime('%b %d, %Y')}"
                new_chat_id = db_manager.create_chat(user_id, welcome_title)
                logger.info("Created welcome chat {new_chat_id} for new user %s", username)
            except Exception as e:
                logger.warning("Failed to create welcome chat for new user {username}: %s", e)
                # Don't fail registration if chat creation fails
            
            logger.info("New user registered: {username} with role {user_role}, session %s", session_id)
            
            access_token = create_access_token(username)
            return {
                "access_token": access_token, 
                "token_type": "bearer", 
                "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
                "session_id": session_id
            }
    except Exception as e:
        logger.error("Registration failed for {username}: %s", e)
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
    # Log login attempt
    client_ip = request.client.host if request and request.client else "unknown"
    log_error("low", "authentication", "backend", "login_attempt",
             f"Login attempt for username: {form_data.username} from IP: {client_ip}")
    
    try:
        with monitor_operation("backend", "user_login", "medium", "authentication"):
            # Get user credentials from database
            user_creds = db_manager.get_user_credentials(form_data.username)
            if not user_creds:
                raise HTTPException(status_code=401, detail="Incorrect username or password")
            
            # Check if user account is active
            if user_creds["status"] != "ACTIVE":
                raise HTTPException(status_code=403, detail="Account is deactivated or suspended")
            
            # Verify password
            computed_hash = hash_password(form_data.password, user_creds["password_salt"])
            if not computed_hash == user_creds["password_hash"]:
                raise HTTPException(status_code=401, detail="Incorrect username or password")
            
            # Update last login
            db_manager.update_last_login(user_creds["user_id"])
            
            # Create session
            ip_address = request.client.host if request else None
            session_id = db_manager.create_session(user_creds["user_id"], ip_address)
            
            # Log audit action
            try:
                db_manager.log_audit_action(user_creds["user_id"], "User logged in: %s" % form_data.username)
            except Exception:
                pass  # Audit logging is optional
            
            # Create a welcome chat only if user has no existing chats
            try:
                existing_chats = db_manager.get_chat_history(user_creds["user_id"], limit=1)
                if not existing_chats:
                    from datetime import datetime
                    welcome_title = f"Welcome Chat - {datetime.now().strftime('%b %d, %Y')}"
                    new_chat_id = db_manager.create_chat(user_creds["user_id"], welcome_title)
                    logger.info("Created welcome chat %s for user %s", new_chat_id, form_data.username)
            except Exception as e:
                logger.warning("Failed to create welcome chat for {form_data.username}: %s", e)
                # Don't fail login if chat creation fails
            
            logger.info("User {form_data.username} logged in, session %s", session_id)
            
            access_token = create_access_token(user_creds["username"])
            return {
                "access_token": access_token, 
                "token_type": "bearer", 
                "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
                "session_id": session_id
            }
    except Exception as e:
        logger.error("Login failed for {form_data.username}: %s", e)
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/login", response_model=Token)
async def login_alias(login_data: LoginRequest, request: Request = None):
    """User login - alias for /token endpoint (mobile app compatibility)"""
    # Create OAuth2PasswordRequestForm-like object
    class FormData:
        def __init__(self, username: str, password: str):
            self.username = username
            self.password = password
    
    form_data = FormData(login_data.username, login_data.password)
    
    # Log login attempt
    client_ip = request.client.host if request and request.client else "unknown"
    log_error("low", "authentication", "backend", "login_attempt",
             f"Login attempt for username: {form_data.username} from IP: {client_ip}")
    
    try:
        with monitor_operation("backend", "user_login", "medium", "authentication"):
            # Get user credentials from database
            user_creds = db_manager.get_user_credentials(form_data.username)
            if not user_creds:
                raise HTTPException(status_code=401, detail="Incorrect username or password")
            
            # Check if user account is active
            if user_creds["status"] != "ACTIVE":
                raise HTTPException(status_code=403, detail="Account is deactivated or suspended")
            
            # Verify password
            computed_hash = hash_password(form_data.password, user_creds["password_salt"])
            if not computed_hash == user_creds["password_hash"]:
                raise HTTPException(status_code=401, detail="Incorrect username or password")
            
            # Update last login
            db_manager.update_last_login(user_creds["user_id"])
            
            # Create session
            ip_address = request.client.host if request else None
            session_id = db_manager.create_session(user_creds["user_id"], ip_address)
            
            # Log audit action
            try:
                db_manager.log_audit_action(user_creds["user_id"], "User logged in: %s" % form_data.username)
            except Exception:
                pass  # Audit logging is optional
            
            # Create a welcome chat only if user has no existing chats
            try:
                existing_chats = db_manager.get_chat_history(user_creds["user_id"], limit=1)
                if not existing_chats:
                    from datetime import datetime
                    welcome_title = f"Welcome Chat - {datetime.now().strftime('%b %d, %Y')}"
                    new_chat_id = db_manager.create_chat(user_creds["user_id"], welcome_title)
                    logger.info("Created welcome chat %s for user %s", new_chat_id, form_data.username)
            except Exception as e:
                logger.warning("Failed to create welcome chat for {form_data.username}: %s", e)
                # Don't fail login if chat creation fails
            
            logger.info("User {form_data.username} logged in, session %s", session_id)
            
            access_token = create_access_token(user_creds["username"])
            return {
                "access_token": access_token, 
                "token_type": "bearer", 
                "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
                "session_id": session_id
            }
    except Exception as e:
        logger.error("Login failed for {form_data.username}: %s", e)
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/logout")
async def logout(request: LogoutRequest = None, user: UserInDB = Depends(get_current_user)):
    # End session if session_id provided
    session_id = request.session_id if request else None
    
    if session_id:
        db_manager.end_session(session_id)
        logger.info("User %s logged out, session %s ended", user.username, session_id)
    else:
        # If no session_id provided, end all active sessions for this user
        logger.info("No session_id provided, ending all sessions for user %s", user.username)
        active_sessions = db_manager.get_active_sessions()
        user_sessions = [s for s in active_sessions if s.get('user_id') == user.user_id]
        for session in user_sessions:
            db_manager.end_session(session['session_id'])
            logger.info("Ended session %s for user %s", session['session_id'], user.username)
    
    # Log audit action
    try:
        if hasattr(user, 'user_id') and user.user_id:
            db_manager.log_audit_action(user.user_id, "User logged out: %s" % user.username)
    except Exception:
        pass
    
    return {"message": "Successfully logged out"}


@app.get("/token-info")
async def get_token_info(user: UserInDB = Depends(get_current_user)):
    """
    Get current user's token usage information
    Returns max tokens, used tokens, remaining tokens, and usage percentage
    """
    # Guest users don't have token tracking
    if user.username == "guest":
        return {
            "is_guest": True,
            "message": "Guest users have unlimited access to Phi-2 model",
            "max_tokens": None,
            "used_tokens": None,
            "remaining_tokens": None,
            "usage_percentage": None
        }
    
    # Get user ID
    if not hasattr(user, 'user_id') or not user.user_id:
        raise HTTPException(status_code=400, detail="User ID not available")
    
    try:
        # Get token info from database
        token_info = db_manager.get_user_token_limit(user.user_id)
        
        if not token_info:
            # User doesn't have token record - create one
            db_manager.create_token_limit(user.user_id)
            token_info = db_manager.get_user_token_limit(user.user_id)
        
        if not token_info:
            raise HTTPException(status_code=500, detail="Failed to retrieve token information")
        
        max_tokens = token_info.get('max_tokens', 0)
        used_tokens = token_info.get('used_tokens', 0)
        remaining_tokens = max(0, max_tokens - used_tokens)
        usage_percentage = round((used_tokens / max_tokens * 100), 2) if max_tokens > 0 else 0
        
        return {
            "is_guest": False,
            "max_tokens": max_tokens,
            "used_tokens": used_tokens,
            "remaining_tokens": remaining_tokens,
            "usage_percentage": usage_percentage,
            "status": "active" if remaining_tokens > 0 else "limit_reached"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting token info: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve token information: {str(e)}")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@app.post("/change-password")
async def change_password(password_data: PasswordChange, user: UserInDB = Depends(get_current_user)):
    """Allow users to change their own password"""
    if user.username == "guest":
        raise HTTPException(status_code=403, detail="Guest users cannot change password")
    
    if not hasattr(user, 'user_id') or not user.user_id:
        raise HTTPException(status_code=400, detail="User ID not available")
    
    try:
        # Get user credentials to verify current password
        user_creds = db_manager.get_user_credentials(user.username)
        if not user_creds:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify current password
        computed_hash = hash_password(password_data.current_password, user_creds["password_salt"])
        if computed_hash != user_creds["password_hash"]:
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        
        # Validate new password
        if len(password_data.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
        
        # Generate new salt and hash
        import secrets
        new_salt = secrets.token_hex(16)
        new_hash = hash_password(password_data.new_password, new_salt)
        
        # Update password in database
        success = db_manager.update_user_password(user.user_id, new_hash, new_salt)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update password")
        
        # Log the action
        db_manager.log_audit_action(user.user_id, "User changed password: %s" % user.username)
        logger.info("User %s changed their password", user.username)
        
        return {
            "success": True,
            "message": "Password changed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error changing password: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@app.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Request password reset - generates token and sends email"""
    try:
        # Find user by email
        user = db_manager.get_user_by_email(request.email)
        if not user:
            # Don't reveal if email exists (security)
            return {
                "success": True,
                "message": "If that email exists, a reset link has been sent"
            }
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        
        # Store token in database (expires in 1 hour)
        success = db_manager.create_password_reset_token(user['user_id'], reset_token)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to generate reset token")
        
        # Log to audit so admin can see who requested a reset
        try:
            db_manager.log_audit_action(user['user_id'], "password_reset_requested", user['user_id'], "users")
        except Exception:
            pass
        
        # Try to send email (if configured)
        try:
            send_password_reset_email(request.email, user['username'], reset_token)
            logger.info("Password reset email sent to %s", request.email)
        except Exception as e:
            logger.warning("Failed to send email: {e}. Token: %s", reset_token)
            # Continue anyway - admin can see token in database
        
        return {
            "success": True,
            "message": "If that email exists, a reset link has been sent",
            "token": None  # Never expose token in API response — check DB or logs for testing
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in forgot password: %s", e)
        raise HTTPException(status_code=500, detail="Failed to process request")


@app.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using token"""
    try:
        # Validate token
        token_data = db_manager.validate_reset_token(request.token)
        if not token_data:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
        # Validate new password
        if len(request.new_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        # Generate new salt and hash
        new_salt = secrets.token_hex(16)
        new_hash = hash_password(request.new_password, new_salt)
        
        # Update password
        success = db_manager.update_user_password(token_data['user_id'], new_hash, new_salt)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update password")
        
        # Mark token as used
        db_manager.mark_reset_token_used(request.token)
        
        # Log the action
        db_manager.log_audit_action(token_data['user_id'], "Password reset via email token")
        logger.info("Password reset for user_id %s", token_data['user_id'])
        
        return {
            "success": True,
            "message": "Password reset successfully. You can now login with your new password."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting password: %s", e)
        raise HTTPException(status_code=500, detail="Failed to reset password")


def send_password_reset_email(email: str, username: str, token: str):
    """Send password reset email (placeholder - configure SMTP)"""
    # TODO: Configure SMTP settings
    # For now, just log the token
    reset_link = f"http://localhost:8080/?token={token}"
    logger.info("[RESET] PASSWORD RESET LINK for {username}: %s", reset_link)
    
    # Uncomment and configure when SMTP is ready:
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = email
    msg['Subject'] = "FAIA - Password Reset Request"
    
    body = f'''
    Hello {username},
    
    You requested a password reset for your FAIA account.
    
    Click the link below to reset your password:
    {reset_link}
    
    This link will expire in 1 hour.
    
    If you didn't request this, please ignore this email.
    
    Best regards,
    FAIA Team
    '''
    
    msg.attach(MIMEText(body, 'plain'))
    
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(smtp_user, smtp_password)
    server.send_message(msg)
    server.quit()
    """

@app.post("/qwen")
async def qwen_endpoint(request: PromptRequest):
    """Qwen endpoint"""
    prompt = request.prompt
    try:
        # Check if model is available using model_service
        if not model_service.is_model_loaded():
            raise HTTPException(status_code=503, detail="Qwen model not loaded")
        
        # Generate response using Qwen via model_service
        use_rag = bool(getattr(request, 'use_rag', False))
        course_code = getattr(request, 'course_code', None) if use_rag else None
        response = generate_qwen_response(prompt, use_rag=use_rag, course_code=course_code)
        
        return {"response": response}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Error in Qwen endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# Additional endpoints can be added here if needed

@app.post("/chat")
async def chat(request: PromptRequest, user: UserInDB = Depends(get_current_user), req: Request = None):
    model = "qwen"  # Only Qwen model supported
    prompt = sanitize_input(request.prompt)  # Sanitize user input
    
    # DETAILED REQUEST TRACKING - Find who's calling!
    client_ip = req.client.host if req and req.client else "unknown"
    user_agent = req.headers.get("user-agent", "unknown") if req else "unknown"
    referer = req.headers.get("referer", "none") if req else "none"
    auth_header = "present" if req and req.headers.get("authorization") else "MISSING"
    
    logger.info("CHAT REQUEST | User: {user.username} | Model: {model} | IP: %s", client_ip)
    logger.info("   Auth: {auth_header} | Referer: %s", referer)
    logger.info("   User-Agent: %s", user_agent[:100])
    logger.info("   Prompt: %s...", prompt[:50])
    
    # Start error monitoring for this request
    request_context = {
        "user": user.username,
        "model": model,
        "client_ip": client_ip,
        "user_agent": user_agent[:100],
        "prompt_length": len(prompt)
    }
    
    try:
        with monitor_operation("backend", "chat_request", "high", "api"):
            # CHECK IF USER IS SUSPENDED
            if user.username != "guest" and hasattr(user, 'user_id') and user.user_id:
                user_status = db_manager.get_user_status(user.user_id)
                if user_status == 'suspended':
                    logger.warning("BLOCKED: Suspended user %s attempted to chat", user.username)
                    raise HTTPException(
                        status_code=403,
                        detail="Your account has been suspended. Please contact an administrator."
                    )
            
            # Chat request processing
            
            # Guest users can only use qwen (for quick testing/demos on local machine)
            if user.username == "guest":
                model = "qwen"  # Guests limited to Qwen
                logger.info("Guest user using Qwen (limited access)")
            
            # STRICT SESSION VALIDATION - Terminated sessions are BLOCKED
            if user.username != "guest" and hasattr(user, 'user_id') and user.user_id:
                # Check if session_id is provided
                session_id = getattr(request, 'session_id', None)
                
                logger.info("Validating session for user %s: session_id=%s, user_id=%s", user.username, session_id, user.user_id)
                
                if session_id and session_id != 'web_session':
                    # Validate that the session is still active
                    try:
                        session_id_int = int(session_id)
                        is_valid = db_manager.is_session_valid(session_id_int, user.user_id)
                        logger.info("Session {session_id} validation result: %s", is_valid)
                        
                        if not is_valid:
                            logger.warning("BLOCKED: Session %s is terminated for user %s", session_id, user.username)
                            raise HTTPException(
                                status_code=403,
                                detail="Your session has been terminated by an administrator. Please log in again."
                            )
                        else:
                            # Session is valid - update activity
                            db_manager.update_session_activity(session_id_int)
                            logger.info("Session %s is VALID for user %s", session_id, user.username)
                    except ValueError as e:
                        # Invalid format - reject
                        logger.warning("BLOCKED: Invalid session_id format: {session_id} - %s", e)
                        raise HTTPException(
                            status_code=401,
                            detail="Invalid session. Please log in again."
                        )
            else:
                # No valid session_id - get or create one
                active_session = db_manager.get_user_active_session(user.user_id)
                if active_session:
                    request.session_id = str(active_session['session_id'])
                    db_manager.update_session_activity(active_session['session_id'])
                    logger.info("Using active session %s for user %s", active_session['session_id'], user.username)
                else:
                    # Create new session (only when no session_id was provided)
                    # Skip session creation for guest users (they don't need database sessions)
                    if user.username != "guest" and hasattr(user, 'user_id') and user.user_id:
                        ip_address = req.client.host if req else None
                        new_session_id = db_manager.create_session(user.user_id, ip_address)
                        request.session_id = str(new_session_id)
                        logger.info("Created new session %s for user %s", new_session_id, user.username)
                    else:
                        logger.info("Skipping session creation for guest user")
        
        # Check token limits for ALL users (including guests)
        estimated_tokens = len(prompt) // 4 + 20  # Add small buffer for response overhead
        guest_token_check_needed = False
        
        if user.username == "guest":
            # Guest: will check in-memory token limit after we have guest_id
            guest_token_check_needed = True
        elif hasattr(user, 'user_id') and user.user_id:
            # Registered user: check their personal token limit
            token_check = db_manager.check_token_limit(user.user_id, estimated_tokens)
            if not token_check["can_use"]:
                raise HTTPException(
                    status_code=429, 
                    detail=f"Token limit exceeded. Remaining: {token_check['remaining_tokens']}, Requested: {estimated_tokens}"
                )
        
        # ==================== PERFORMANCE: CHECK CACHE ====================
        # Try to get cached response for registered users (not guests)
        # Only cache non-RAG responses as RAG materials may change
        cached_response = None
        
        # ==================== CACHE DISABLED ====================
        # Cache is disabled because it doesn't consider conversation history
        # Returning cached responses breaks memory/context in conversations
        # TODO: Implement context-aware caching if needed
        # ==================== END CACHE CHECK ====================
            
        # ==================== EARLY HISTORY LOAD (for file context detection) ====================
        # Load conversation history early so we can detect file context BEFORE RAG runs
        augmented_prompt = prompt
        has_file_context = False
        _early_is_guest = (user.username == "guest")
        _early_chat_id = None
        if not _early_is_guest and hasattr(user, 'user_id') and user.user_id:
            try:
                _early_chat_id = int(getattr(request, 'chat_id', None) or 0) or None
            except (ValueError, TypeError):
                _early_chat_id = None
        if _early_chat_id:
            _early_history = build_chatml_history(str(getattr(request, 'session_id', 'default')), False, _early_chat_id)
            for _msg in _early_history:
                if _msg.get("role") == "system" and "[FILE_CONTEXT:" in _msg.get("content", ""):
                    has_file_context = True
                    logger.info("[FILE] Detected file context in conversation history (early check)")
                    break

        # ==================== RAG MODE ====================
        # PRIORITY: Uploaded file content takes precedence over RAG course materials
        rag_sources = []
        
        # If we have file context, RAG is bypassed for this prompt
        if has_file_context:
            logger.info("File context active - RAG bypassed for user %s", user.username)
        
        # BLOCK RAG FOR GUESTS
        if request.use_rag and user.username == "guest":
            logger.warning("RAG BLOCKED | Guest user attempted to use RAG")
            # Force disable RAG for guests
            request.use_rag = False
        
        if request.use_rag and not has_file_context:
            # Enhanced RAG logging for terminal visibility
            rag_status = "USER ENABLED"
            
            logger.info("RAG MODE ENABLED | User: %s | Status: %s | Course: %s", user.username, rag_status, request.course_code or 'all')
            
            # Search for relevant materials
            search_results = rag_service.search(
                query=prompt,
                course_code=request.course_code,
                top_k=request.rag_top_k or 5
            )
            
            if search_results:
                logger.info("RAG: Found %s relevant chunks", len(search_results))
                
                # Build context from search results
                rag_context = rag_service.build_rag_context(search_results, max_tokens=2000)
                
                logger.info("RAG Context length: {len(rag_context)} chars | Sources: %s", len(search_results))
                # Clean unicode characters for logging
                clean_preview = rag_context[:200].encode('ascii', 'ignore').decode('ascii')
                logger.info("RAG Context preview: %s...", clean_preview)
                
                # Create concise RAG prompt
                rag_preamble = f"""You are FAIA, an AI educational assistant. Your name is FAIA and you help students learn. Answer using ONLY these course materials. Include [Source, Page] citations. Never identify yourself as any other AI model.

MATERIALS:
{rag_context}

Question: """
                
                augmented_prompt = rag_preamble + prompt
                
                # Debug: Log the final prompt being sent to model
                logger.info("Final prompt length: %s chars", len(augmented_prompt))
                logger.info("Final prompt preview: %s...", augmented_prompt[:300])
                
                # Store sources for response
                rag_sources = [{
                    "material_id": r['metadata'].get('material_id'),
                    "original_filename": r['metadata'].get('source_file'),
                    "page_number": r['metadata'].get('page_number'),
                    "text_preview": r['text'][:200] + "..." if len(r['text']) > 200 else r['text']
                } for r in search_results]
                
                # Log RAG query
                if hasattr(user, 'user_id') and user.user_id:
                    db_manager.log_rag_query(
                        user_id=user.user_id,
                        query_text=prompt,
                        course_code=request.course_code or "all",
                        chunks_retrieved=len(search_results),
                        response_generated=True
                    )
            else:
                logger.warning("RAG: No relevant materials found for query")
                # Don't wrap prompt if we have conversation history - just use original prompt
                # The conversation history provides the context
                augmented_prompt = prompt
        else:
            logger.info("RAG DISABLED | User: %s | Using model knowledge only", user.username)
            augmented_prompt = prompt  # Use original prompt without RAG context
        
        # Get response from PHI-2 model (only model supported)
        logger.info("MODEL SELECTED: Qwen | User: %s", user.username)
        
        # Check if model is available — only block if using local provider and model failed to load
        # Ollama and OpenAI providers don't use the local model_loaded flag
        _provider = os.getenv("MODEL_PROVIDER", "local").lower()
        if _provider == "local" and not model_service.is_model_loaded():
            raise HTTPException(
                status_code=503, 
                detail="Qwen model not available. Please check your model setup."
            )
        
        # ==================== MEMORY INTEGRATION ====================
        # Detect if user is guest or registered
        is_guest = (user.username == "guest")
        
        # Determine session ID for memory
        if is_guest:
            # Guest: use IP + User-Agent fingerprint (stable across requests, no cookies needed)
            client_ip = req.client.host if req and req.client else "unknown"
            ua = req.headers.get("user-agent", "") if req else ""
            guest_id = f"guest_{hashlib.md5(f'{client_ip}_{ua}'.encode()).hexdigest()[:16]}"
            session_id_for_memory = guest_id

            # Clear memory if this is the first message after a page load/refresh
            guest_new_page_load = getattr(request, 'guest_new_page_load', False)
            if guest_new_page_load and guest_id in guest_sessions:
                guest_sessions[guest_id] = {"history": [], "last_activity": time.time()}
                logger.info("[MEMORY] Guest %s page refreshed - memory cleared", guest_id)
            logger.info("[MEMORY] Guest ID from fingerprint: %s", guest_id)
        else:
            # Registered: use chat session ID
            session_id_for_memory = str(getattr(request, 'session_id', 'default'))
        
        # Check guest token limit now that we have guest_id
        if is_guest and guest_token_check_needed:
            guest_token_check = check_guest_token_limit(session_id_for_memory, estimated_tokens)
            if not guest_token_check["can_use"]:
                time_remaining = guest_token_check.get("time_remaining_seconds", 0)
                hours = time_remaining // 3600
                minutes = (time_remaining % 3600) // 60
                seconds = time_remaining % 60
                if time_remaining > 3600:
                    wait_msg = f" Try again in {hours}h {minutes}m."
                elif time_remaining > 60:
                    wait_msg = f" Try again in {minutes} minutes."
                elif time_remaining > 0:
                    wait_msg = f" Try again in {seconds} seconds."
                else:
                    wait_msg = f" Limit resets after {int(GUEST_TOKEN_TTL_HOURS * 60)} minutes."
                raise HTTPException(
                    status_code=429,
                    detail=f"Guest token limit reached ({guest_token_check['used_today']}/{guest_token_check['limit']}).{wait_msg} Register for unlimited access."
                )
            logger.info("Guest %s token check: %s/%s used", session_id_for_memory, guest_token_check['used_today'], guest_token_check['limit'])
        
        # Get chat_id for students (needed for database memory)
        chat_id_for_memory = None
        if not is_guest and hasattr(user, 'user_id') and user.user_id:
            chat_id_for_memory = getattr(request, 'chat_id', None)
            if chat_id_for_memory:
                try:
                    chat_id_for_memory = int(chat_id_for_memory)
                except (ValueError, TypeError):
                    chat_id_for_memory = None
        
        # Load conversation history (from database for students, in-memory for guests)
        conversation_history = build_chatml_history(session_id_for_memory, is_guest, chat_id_for_memory)
        logger.info("[MEMORY] Loaded {len(conversation_history)} previous turns for {'guest' if is_guest else 'user'} %s", session_id_for_memory)
        
        # Check if conversation history contains file context (system messages)
        for msg in conversation_history:
            if msg.get("role") == "system" and "[FILE_CONTEXT:" in msg.get("content", ""):
                has_file_context = True
                logger.info("[FILE] Detected file context in conversation history")
                break
        
        if has_file_context:
            augmented_prompt = f"Based on the uploaded file content in our conversation, {prompt}"
            logger.info("[FILE] Enhanced prompt with file context reference")
        
        # Pass is_rag flag and conversation history for generation
        # Use augmented_prompt which includes file context and RAG context
        prompt_for_model = augmented_prompt
        
        response = generate_qwen_response(
            prompt_for_model, 
            is_rag=(request.use_rag and len(rag_sources) > 0),
            conversation_history=conversation_history
        )
            
        # Format response as a single string
        if isinstance(response, list):
            response = " ".join(response)
        
        # Calculate actual token usage (rough approximation)
        actual_tokens = (len(prompt) + len(response)) // 4
        
        # Prepare response data first (before any blocking operations)
        chat_id = None
        
        # For registered users, CREATE CHAT FIRST before saving turn
        if not is_guest and hasattr(user, 'user_id') and user.user_id:
            # Get or validate existing chat_id
            chat_id = getattr(request, 'chat_id', None)
            
            # Validate chat_id is an integer, not a string like 'web_session'
            if chat_id:
                try:
                    chat_id = int(chat_id)
                except (ValueError, TypeError):
                    # Invalid chat_id, will create new chat
                    chat_id = None
            
            # Create new chat if needed (BEFORE save_turn)
            if not chat_id:
                # No chat_id sent = new chat requested, always create one
                title = prompt[:50] + "..." if len(prompt) > 50 else prompt
                chat_id = db_manager.create_chat(user.user_id, title)
                chat_id_for_memory = chat_id
                logger.info("Created new chat %s for first message from user %s", chat_id, user.username)
        
        # Save conversation turn to memory (database for students, in-memory for guests)
        # NOW chat_id is guaranteed to exist for registered users
        save_turn(session_id_for_memory, prompt, response, is_guest, chat_id_for_memory)
        logger.info("[MEMORY] Saved conversation turn for {'guest' if is_guest else 'user'} %s", session_id_for_memory)
        
        # Update guest token usage after successful response
        if is_guest and guest_token_check_needed:
            # Estimate actual tokens used (prompt + response)
            actual_tokens_used = estimated_tokens + (len(response) // 4)
            update_guest_token_usage(session_id_for_memory, actual_tokens_used)
        
        # Skip database for guest users - they get no persistence
        if user.username == "guest":
            # Guest users get response with memory but no database storage
            result = {
                "success": True,
                "response": response,
                "is_guest": True,
                "message": "Guest mode - conversation memory active for this session!"
            }
            return result
        
        # ==================== RESPONSE VALIDATION ====================
        # ==================== IMMEDIATE RESPONSE DELIVERY ====================
        # Chat already created above before save_turn - no need to create again
        
        # Return response immediately - no blocking operations
        result = {
            "success": True,
            "response": response,
            "model_used": model,
            "tokens_used": actual_tokens,
            "rag_mode": "enabled" if request.use_rag else "disabled",
            "cached": False  # This is a fresh response
        }
        if chat_id:
            result["chat_id"] = chat_id
        
        # Add RAG sources if RAG mode was used
        if request.use_rag and rag_sources:
            result["rag_enabled"] = True
            result["sources"] = rag_sources
            result["source_count"] = len(rag_sources)
        
        # ==================== BACKGROUND PROCESSING ====================
        # Schedule database and cache operations in background (non-blocking)
        if user.username != "guest" and hasattr(user, 'user_id') and user.user_id:
            # Use asyncio to run background tasks without blocking response
            asyncio.create_task(
                _save_chat_background(
                    user_id=user.user_id,
                    username=user.username,
                    chat_id=chat_id,
                    prompt=prompt,
                    response=response,
                    actual_tokens=actual_tokens,
                    model=model,
                    use_rag=request.use_rag,
                    request_session_id=getattr(request, 'session_id', None)
                )
            )
        
        # Final summary log for terminal visibility
        final_rag_status = result["rag_mode"]
        sources_used = len(rag_sources) if rag_sources else 0
        logger.info("RESPONSE GENERATED | User: {user.username} | RAG: {final_rag_status.upper()} | Sources: {sources_used} | Model: {model.upper()} | Tokens: {actual_tokens} | Length: %s chars", len(response))
        
        return result
        
    except HTTPException as he:
        # Allow HTTPException to pass through unchanged
        raise he
    except Exception as e:
        logger.error("Error in chat endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


async def _save_chat_background(user_id: int, username: str, chat_id: int, prompt: str, 
                               response: str, actual_tokens: int, model: str, 
                               use_rag: bool, request_session_id: str = None):
    """Background task to save chat data without blocking response delivery"""
    try:
        # Chat is already created in main flow before save_turn - no need to create here
        # This ensures chat_id exists before messages are saved
        
        # Update session with chat_id
        if request_session_id:
            try:
                session_id_int = int(request_session_id)
                db_manager.update_session_chat(session_id_int, chat_id)
            except (ValueError, TypeError):
                # Try to find active session
                active_sessions = db_manager.get_active_sessions()
                user_sessions = [s for s in active_sessions if s.get('user_id') == user_id]
                if user_sessions:
                    latest_session = user_sessions[0]
                    db_manager.update_session_chat(latest_session['session_id'], chat_id)
        
        # Messages are already saved by save_turn() function - no need to save again here
        # Removed duplicate save to prevent double entries in database
        
        # Update token usage
        db_manager.update_token_usage(user_id, actual_tokens)
        
        # Cache response for future use (only non-RAG responses)
        # BP-NEW-8: Disabled - cache reads are already bypassed, no point growing the table
        # if not use_rag:
        #     cache_manager.set_chat_response(
        #         prompt=prompt,
        #         model=model,
        #         response=response,
        #         use_rag=False,
        #         course_code=None,
        #         quality_score=0.5
        #     )
        #     logger.info("Background: Cached response for user %s", username)
        
        logger.info("Background: Saved chat for user {username}, tokens used: %s", actual_tokens)
        
    except Exception as e:
        logger.error("Background task error for user {username}: %s", e)
        # Don't raise - background tasks should not crash


# User Feedback System for Quality-Based Caching
class FeedbackRequest(BaseModel):
    message_id: Optional[int] = None
    chat_id: Optional[int] = None
    prompt: str
    response: str
    is_helpful: bool  # True = good response, False = bad response
    feedback_notes: Optional[str] = None


@app.post("/feedback")
async def submit_feedback(feedback: FeedbackRequest, user: UserInDB = Depends(get_current_user)):
    """Submit feedback on AI response quality for improved caching"""
    if user.username == "guest":
        return {"message": "Feedback not available for guest users"}
    
    if not hasattr(user, 'user_id') or not user.user_id:
        raise HTTPException(status_code=400, detail="User ID not available")
    
    try:
        # Handle like/unlike toggle
        if feedback.is_helpful:
            # Cache the good response
            cache_manager.set_chat_response(
                prompt=feedback.prompt,
                model="qwen",  # Default model
                response=feedback.response,
                use_rag=False,
                course_code=None,
                quality_score=1.0  # High quality based on user feedback
            )
            logger.info("User %s liked response - cached for reuse", user.username)
            action = "cached"
        else:
            # Remove from cache (unlike or negative feedback)
            cache_manager.remove_chat_response(feedback.prompt)
            logger.info("User %s unliked response - removed from cache", user.username)
        
        # Log feedback for analysis
        db_manager.log_audit_action(
            user.user_id, 
            f"Feedback: {'Helpful' if feedback.is_helpful else 'Not helpful'} - {feedback.feedback_notes or 'No notes'}"
        )
        
        return {
            "success": True,
            "message": "Thank you for your feedback! This helps improve response quality.",
            "action": action
        }
        
    except Exception as e:
        logger.error("Error processing feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to process feedback")



@app.get("/chat/history")
async def get_chat_history(user: UserInDB = Depends(get_current_user)):
    if user.username == "guest":
        # For anonymous users, return empty history
        return {"history": []}
    
    if not hasattr(user, 'user_id') or not user.user_id:
        return {"history": []}
    
    try:
        # Get chat history from database
        chats = db_manager.get_chat_history(user.user_id)
        
        # Get messages for each chat (limit to 100 most recent for UI performance)
        for chat in chats:
            messages = db_manager.get_chat_messages(chat['chat_id'], limit=100)
            chat['messages'] = messages
        
        return {"history": chats}
    except Exception as e:
        logger.error("Error getting chat history: %s", e)
        return {"history": []}

@app.delete("/chat/history", response_model=ResetResponse)
async def complete_user_reset(user: UserInDB = Depends(get_current_user)):
    """
    COMPLETE USER RESET: Clear ALL user data and fully restore tokens.
    
    This comprehensive reset includes:
    - Delete all chat history and messages
    - End all active sessions
    - Clear uploaded files from memory
    - Restore ALL tokens to full quota
    - Reset user to fresh state
    
    Perfect for students who want a clean slate to manage both storage and tokens.
    """
    try:
        # Debug logging to identify the issue
        logger.info("DELETE /chat/history called by user: %s", getattr(user, 'username', 'UNKNOWN'))
        
        if not user:
            logger.error("User object is None")
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if user.username == "guest":
            return ResetResponse(success=True, message="No history to clear for guest user")
        
        if not hasattr(user, 'user_id') or not user.user_id:
            logger.warning("User %s missing user_id attribute", user.username)
            return ResetResponse(success=False, message="No user ID available")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in user validation: %s", e)
        raise HTTPException(status_code=400, detail=f"User validation error: {str(e)}")
    
    try:
        # COMPREHENSIVE RESET - Clean everything for fresh start
        logger.info("Starting complete reset for user %s (ID: %s)", user.username, user.user_id)
        
        # 1. Get all chats and calculate total tokens
        chats = db_manager.get_chat_history(user.user_id)
        total_tokens = 0
        deleted_count = 0
        
        for chat in chats:
            messages = db_manager.get_chat_messages(chat['chat_id'])
            chat_tokens = sum(msg.get('token_count', 0) for msg in messages)
            total_tokens += chat_tokens
            
            logger.info("Chat {chat['chat_id']}: %s messages, {chat_tokens} tokens", len(messages))
            db_manager.delete_chat(chat['chat_id'])
            deleted_count += 1
        
        # 2. End ALL active sessions for this user
        sessions = db_manager.get_active_sessions()
        sessions_ended = 0
        for session in sessions:
            if session.get('user_id') == user.user_id:
                db_manager.end_session(session['session_id'])
                sessions_ended += 1
        
        # 3. Clear uploaded files from memory (file_db is in-memory only)
        files_cleared = 0
        session_keys_to_remove = []
        for session_key, files in file_db.items():
            # Check if any files belong to this user (approximate check)
            if files:  # If there are files in this session
                session_keys_to_remove.append(session_key)
                files_cleared += len(files)
        
        for session_key in session_keys_to_remove:
            del file_db[session_key]
        
        # 4. FULL TOKEN RESET - Return all used tokens to restore full quota
        tokens_returned = 0
        if total_tokens > 0:
            try:
                success = db_manager.return_tokens(user.user_id, total_tokens)
                if success:
                    tokens_returned = total_tokens
                    logger.info("Returned %s tokens to user %s", total_tokens, user.username)
                else:
                    logger.warning("Failed to return tokens for user %s", user.username)
            except Exception as e:
                logger.error("Error returning tokens: %s", e)
        
        # 5. Clear any cached data related to this user
        try:
            # Clear cache entries if cache manager supports it
            if hasattr(cache_manager, 'clear_by_pattern'):
                cache_manager.clear_by_pattern(f"*{user.username}*")
            elif hasattr(cache_manager, 'clear_all'):
                # Fallback to clearing all cache
                cache_manager.clear_all()
                logger.info("Cleared all cache as fallback")
        except Exception as e:
            logger.warning("Could not clear cache: %s", e)
        
        logger.info("COMPLETE RESET for %s: %s chats, %s tokens, %s sessions, %s files", user.username, deleted_count, tokens_returned, sessions_ended, files_cleared)
        
        return ResetResponse(
            success=True,
            message=f"Complete reset successful! Deleted {deleted_count} chats, cleared {files_cleared} files, ended {sessions_ended} sessions, and restored {tokens_returned} tokens. Fresh start ready!",
            chats_deleted=deleted_count,
            tokens_recovered=tokens_returned,
            tokens_returned=tokens_returned,
            sessions_ended=sessions_ended,
            files_cleared=files_cleared
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error("Error clearing chat history: %s", e)
        logger.error("Exception type: %s", type(e))
        logger.error("Exception args: %s", e.args)
        raise HTTPException(status_code=500, detail=f"Failed to clear chat history: {str(e)}")

@app.post("/chat/new")
async def create_new_chat(user: UserInDB = Depends(get_current_user)):
    """Create a new chat session for the user"""
    if user.username == "guest":
        return {"message": "Guests use session-based chats", "chat_id": None}
    
    if not hasattr(user, 'user_id') or not user.user_id:
        raise HTTPException(status_code=400, detail="User ID not available")
    
    try:
        # Create new chat with default title
        title = f"New Chat - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        chat_id = db_manager.create_chat(user.user_id, title)
        
        if chat_id:
            logger.info("Created new chat %s for user %s", chat_id, user.username)
            return {
                "success": True,
                "chat_id": chat_id,
                "title": title,
                "message": "New chat created successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create new chat")
            
    except Exception as e:
        logger.error("Error creating new chat for user {user.username}: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create new chat")

@app.delete("/chat/{chat_id}")
async def delete_chat(chat_id: int, user: UserInDB = Depends(get_current_user), request: Request = None):
    """
    Delete a specific chat and restore tokens to user. Also ends the session.
    
    STUDENT-FRIENDLY: Tokens ARE restored when deleting chats.
    This allows students to clean up their history and recover their quota.
    Educational environment should be forgiving and encourage experimentation.
    """
    if user.username == "guest":
        return {"message": "Guests cannot delete chats"}
    
    if not hasattr(user, 'user_id') or not user.user_id:
        raise HTTPException(status_code=400, detail="User ID not available")
    
    try:
        # Get chat to verify ownership and calculate tokens
        chat = db_manager.get_chat_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        if chat.get('user_id') != user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this chat")
        
        # Get all messages in the chat to calculate total tokens used
        messages = db_manager.get_chat_messages(chat_id)
        total_tokens = sum(msg.get('token_count', 0) for msg in messages)
        
        # Debug logging
        logger.info("Deleting chat {chat_id}: %s messages, {total_tokens} tokens to recover", len(messages))
        
        # Delete the chat (this will cascade delete messages)
        db_manager.delete_chat(chat_id)
        
        # RESTORE TOKENS - student-friendly approach
        # Students can clean up and recover their quota
        if total_tokens > 0:
            db_manager.return_tokens(user.user_id, total_tokens)
            logger.info("Returned {total_tokens} tokens to student {user.username} after deleting chat %s", chat_id)
        
        return {
            "success": True,
            "message": f"Chat deleted and {total_tokens} tokens recovered. Clean up your history to manage your token quota!",
            "tokens_recovered": total_tokens,
            "action": "token_recovery"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting chat: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")



@app.get("/user/tokens")
async def get_user_tokens(user: UserInDB = Depends(get_current_user)):
    """Get user's token usage and limits"""
    if user.username == "guest":
        guest_limit = db_manager.get_guest_token_limit()
        return {
            "max_tokens": guest_limit,
            "used_tokens": 0,
            "remaining_tokens": guest_limit,
            "usage_percentage": 0,
            "is_guest": True
        }
    
    if not hasattr(user, 'user_id') or not user.user_id:
        raise HTTPException(status_code=400, detail="User ID not available")
    
    try:
        token_info = db_manager.get_user_token_limit(user.user_id)
        token_info["is_guest"] = False
        return token_info
    except Exception as e:
        logger.error("Error getting token info: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get token information")



@app.get("/user/files")
async def get_user_files(user: UserInDB = Depends(get_current_user)):
    """Get files uploaded by the user - files are temporary, not stored in DB"""
    # Files are stored in-memory only, not in database
    return {"files": []}

@app.post("/report")
async def report_content_redirect(
    target_type: str = Form(...),
    target_id: str = Form(...),
    report_type: str = Form(...),
    reason: str = Form(...),
    content_preview: str = Form(None),
    user: UserInDB = Depends(get_current_user)
):
    """
    DEPRECATED: Old moderation system replaced with feedback system
    This endpoint now redirects to the new feedback-based quality system
    """
    try:
        if user.username == "guest":
            return {
                "success": False,
                "message": "Guest users cannot provide feedback. Please register or login.",
                "redirect": "Please use the new feedback system instead of reporting."
            }
        
        # Convert old report to new feedback format
        # If user is reporting as "inappropriate" or negative, treat as negative feedback
        is_helpful = report_type not in ["spam", "harassment", "inappropriate", "misinformation", "hate_speech", "violence"]
        
        # For now, return a message directing users to the new system
        return {
            "success": True,
            "message": "Thank you for your feedback! We've moved to a new quality-based feedback system.",
            "new_system": {
                "description": "Instead of reporting, you can now rate responses as helpful or not helpful.",
                "helpful_action": "Click [HELPFUL] if the response was helpful (saves to cache)",
                "benefit": "This helps improve response quality for all users!"
            },
            "legacy_feedback_processed": True,
            "is_helpful_interpretation": is_helpful,
            "feedback_notes": f"Legacy report: {report_type} - {reason}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reporting content: %s", e)
        raise HTTPException(status_code=500, detail="Failed to report content")

@app.get("/moderation/reports")
async def get_moderation_reports(user: UserInDB = Depends(get_current_user)):
    """Get pending moderation reports (admin only)"""
    if user.username == "guest" or not hasattr(user, 'role') or user.role != 'ADMIN':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        reports = db_manager.get_pending_moderation_reports()
        return {"reports": reports}
    except Exception as e:
        logger.error("Error getting moderation reports: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get moderation reports")

@app.post("/upload")
async def upload_file(
    session_id: str = Form(...),
    chat_id: str = Form(None),  # Chat ID for scoping file context
    file: UploadFile = File(...),
    file_type: str = Form("study_material", description="Type of study material (e.g., 'lecture_notes', 'assignment', 'project', 'study_material')"),
    description: str = Form(None, description="Optional description of the file"),
    user: UserInDB = Depends(get_current_user)
):
    try:
        # Validate session_id
        if not session_id or len(session_id) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session ID"
            )

        # Validate file type
        allowed_types = ['lecture_notes', 'assignment', 'project', 'study_material']
        if file_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Must be one of: {', '.join(allowed_types)}"
            )

        # Print received data for debugging
        # Processing file upload

        # Validate filename
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename provided"
            )

        # Validate file size
        file_size = 0
        content = bytearray()
        while chunk := await file.read(8192):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Maximum size is {MAX_FILE_SIZE/1024/1024}MB"
                )
            content.extend(chunk)

        # Validate file type
        mime_type, _ = mimetypes.guess_type(file.filename)
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES.keys())}"
            )

        # Create safe filename — strip path components from original filename to prevent traversal
        timestamp = int(time.time())
        safe_name = Path(file.filename).name  # keeps only the filename, strips any ../ or path
        safe_filename = f"{file_type}_{timestamp}_{safe_name}"
        file_location = UPLOAD_DIR / safe_filename

        # Ensure upload directory exists
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        # Save file
        try:
            with open(file_location, "wb") as f:
                f.write(content)
        except Exception as e:
            logger.error("Error saving file: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
            )

        # Store file info in database and in-memory for session access
        file_info = {
            "filename": file.filename,
            "filepath": str(file_location),
            "uploaded_at": time.time(),
            "uploaded_by": user.username,
            "mime_type": mime_type,
            "size": file_size,
            "file_type": file_type,
            "description": description,
            "session_id": session_id
        }
        
        try:
            # Only create new chat if no chat_id provided AND user is not guest
            created_new_chat = False
            
            logger.info("Upload: chat_id=%s, username=%s, has_user_id=%s, user_id=%s", chat_id, user.username, hasattr(user, 'user_id'), getattr(user, 'user_id', None))
            
            if not chat_id and user.username != "guest" and hasattr(user, 'user_id') and user.user_id:
                # Create new chat for this file upload
                title = f"📎 {file.filename}"
                chat_id = str(db_manager.create_chat(user.user_id, title))
                created_new_chat = True
                logger.info("Created new chat %s for file upload: %s", chat_id, file.filename)
            
            if chat_id:
                try:
                    chat_id_int = int(chat_id)
                    
                    # Extract text content from file
                    extracted_text = _extract_text_for_context(file_info)
                    
                    if extracted_text and extracted_text.strip():
                        # Truncate to reasonable size (2000 chars)
                        if len(extracted_text) > 2000:
                            extracted_text = extracted_text[:2000] + "\n... (content truncated)"
                        
                        # Save as SYSTEM message (hidden from user, only for bot context)
                        # Format: [FILE_CONTEXT] prefix so frontend can identify and hide it
                        file_message = f"[FILE_CONTEXT:{file.filename}]\n\n{extracted_text}"
                        token_count = len(file_message) // 4
                        
                        db_manager.save_message(chat_id_int, 'system', file_message, token_count)
                        
                        logger.info("File content extracted and saved as SYSTEM message in chat {chat_id_int}: {file.filename} (%s chars)", len(extracted_text))
                    else:
                        # No text extracted, just save file metadata as system message
                        file_message = f"[FILE_CONTEXT:{file.filename}] ({mime_type}, {file_size} bytes)"
                        token_count = len(file_message) // 4
                        
                        db_manager.save_message(chat_id_int, 'system', file_message, token_count)
                        
                        logger.info("File metadata saved as SYSTEM message in chat %s: %s", chat_id_int, file.filename)
                    
                except (ValueError, TypeError) as e:
                    logger.warning("Invalid chat_id format: {chat_id}, file content not saved to chat: %s", e)
                except Exception as e:
                    logger.error("Error extracting/saving file content: %s", e)
            else:
                logger.info("No chat_id provided and user is guest, file uploaded but content not saved to chat: %s", file.filename)
            
            # Keep in file_db for backward compatibility
            session_files = file_db.setdefault(session_id, [])
            session_files.append(file_info)
            
        except Exception as e:
            logger.error("Error storing file info: %s", e)
            # Try to clean up the uploaded file
            try:
                os.remove(file_location)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store file information"
            )

        response_data = {
            "success": True,
            "message": "Study material uploaded successfully",
            "file": file_info,
            "display_as_card": True,  # Tell frontend to render as card, not raw text
            "card_text": f"📎 File uploaded: {file.filename}",  # Clean display text
            "extracted_length": len(extracted_text) if 'extracted_text' in locals() else 0
        }
        
        # Include chat_id if we created one or used existing
        if chat_id:
            response_data["chat_id"] = int(chat_id)
            response_data["created_new_chat"] = created_new_chat
        
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error during file upload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during file upload: {str(e)}"
        )

@app.get("/files/{session_id}")
async def list_files(
    session_id: str,
    file_type: str = None,
    user: UserInDB = Depends(get_current_user)
):
    files = file_db.get(session_id, [])
    if file_type:
        files = [f for f in files if f.get("file_type") == file_type]
    return {"files": files}

@app.post("/test-qwen")
async def test_qwen_endpoint(request: PromptRequest):
    """Test Qwen endpoint using centralized model service"""
    prompt = request.prompt
    try:
        response = generate_qwen_response(prompt, use_rag=False)
        return {
            "response": response,
            "model_info": {
                "model_loaded": model_service.is_model_loaded(),
                "model_path": MODEL_PATH,
                "model_type": "Qwen-1.5-4B-Chat"
            },
            "test_mode": True
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Error in test-qwen endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# Text extraction functions moved to rag_service.py to eliminate duplication
# Use rag_service.extract_text() for all text extraction needs

@app.post("/analyze-file")
async def analyze_file(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    file_type: str = Form(...),
    user: UserInDB = Depends(get_current_user)
):
    """
    File analysis endpoint.
    NOTE: Pending rewrite - previous implementation used model globals that are
    no longer valid after the model_service refactor. Use /upload to attach
    files to a chat for context instead.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="File analysis is pending rewrite. Use /upload to attach files to a chat instead."
    )


# Admin endpoints for basic system information
@app.get("/admin")
async def admin_redirect():
    """Redirect to admin panel"""
    return {
        "message": "Admin panel is available at http://localhost:3000",
        "admin_url": "http://localhost:3000",
        "api_docs": "http://localhost:8000/docs"
    }

@app.get("/model/status")
async def get_model_status():
    """Get Qwen model status"""
    return {
        "success": True,
        "model_loaded": model_service.is_model_loaded(),
        "model_path": MODEL_PATH,
        "model_type": "Qwen-1.5-4B-Chat",
        "endpoints_available": {
            "qwen": "/qwen",
            "chat": "/chat", 
            "test_qwen": "/test-qwen"
        }
    }



@app.get("/admin/system/resources")
async def admin_system_resources():
    """System resource information for admin panel"""
    import psutil
    try:
        return {
            "cpu_usage": psutil.cpu_percent(interval=1),
            "memory_usage": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent if hasattr(psutil.disk_usage('/'), 'percent') else 50,
            "disk_free": psutil.disk_usage('/').free // (1024**3) if hasattr(psutil.disk_usage('/'), 'free') else 100,
            "requests_per_min": 10,  # Placeholder
            "avg_response_time": 150,  # Placeholder
            "error_rate": 0.1,  # Placeholder
            "db_connections": 1  # Placeholder
        }
    except ImportError:
        # psutil not available, return mock data
        return {
            "cpu_usage": 25,
            "memory_usage": 60,
            "disk_usage": 45,
            "disk_free": 100,
            "requests_per_min": 10,
            "avg_response_time": 150,
            "error_rate": 0.1,
            "db_connections": 1
        }
    except Exception as e:
        logger.error("Resource check error: %s", e)
        return {
            "cpu_usage": 0,
            "memory_usage": 0,
            "disk_usage": 0,
            "disk_free": 0,
            "requests_per_min": 0,
            "avg_response_time": 0,
            "error_rate": 0,
            "db_connections": 0
        }


# ==================== SESSION MANAGEMENT ENDPOINTS ====================

@app.get("/admin/sessions/active")
async def get_active_sessions():
    """Get all active sessions for admin panel"""
    try:
        sessions = db_manager.get_active_sessions()
        return {
            "active_sessions": sessions,
            "count": len(sessions)
        }
    except Exception as e:
        logger.error("Error getting active sessions: %s", e)
        return {"active_sessions": [], "count": 0}


@app.get("/admin/sessions")
async def get_all_sessions_for_admin(q: str = None, status: str = None, limit: int = 100):
    """Get all sessions for admin panel (matches frontend expectations)"""
    try:
        sessions = db_manager.get_all_sessions(limit)
        
        # Filter by search query
        if q:
            q_lower = q.lower()
            sessions = [s for s in sessions if 
                       q_lower in s.get('username', '').lower() or
                       q_lower in s.get('email', '').lower() or
                       q_lower in str(s.get('session_id', '')) or
                       q_lower in s.get('ip_address', '').lower()]
        
        # Filter by status
        if status:
            if status == 'active':
                sessions = [s for s in sessions if not s.get('logout_time')]
            elif status == 'completed':
                sessions = [s for s in sessions if s.get('logout_time')]
            elif status == 'inactive':
                sessions = [s for s in sessions if s.get('status') == 'inactive']
        
        return sessions
    except Exception as e:
        logger.error("Error getting sessions: %s", e)
        return []


@app.get("/admin/sessions/all")
async def get_all_sessions(limit: int = 100):
    """Get all sessions (active and ended) for admin panel"""
    try:
        sessions = db_manager.get_all_sessions(limit)
        active_count = sum(1 for s in sessions if s.get('status') == 'active' and not s.get('logout_time'))
        return {
            "sessions": sessions,
            "total": len(sessions),
            "active": active_count,
            "ended": len(sessions) - active_count
        }
    except Exception as e:
        logger.error("Error getting all sessions: %s", e)
        return {"sessions": [], "total": 0, "active": 0, "ended": 0}


@app.get("/user/sessions")
async def get_user_sessions_endpoint(user: UserInDB = Depends(get_current_user)):
    """Get sessions for the current user"""
    if not hasattr(user, 'user_id') or not user.user_id:
        raise HTTPException(status_code=400, detail="User ID not available")
    
    try:
        sessions = db_manager.get_user_sessions(user.user_id)
        return {"sessions": sessions}
    except Exception as e:
        logger.error("Error getting user sessions: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get sessions")


# ==================== PERFORMANCE MONITORING ENDPOINTS ====================

@app.get("/admin/cache/stats")
async def get_cache_statistics(user: UserInDB = Depends(get_current_user)):
    """Get cache performance statistics (admin only)"""
    # Check if user is admin
    if hasattr(user, 'role') and user.role not in ['ADMIN', 'PROFESSOR']:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view cache statistics"
        )
    
    try:
        stats = cache_manager.get_stats()
        
        return {
            "success": True,
            "stats": stats,
            "recommendations": _get_cache_recommendations(stats)
        }
    except Exception as e:
        logger.error("Error getting cache stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/cache/clear")
async def clear_cache(user: UserInDB = Depends(get_current_user), cache_type: Optional[str] = None):
    """Clear cache (admin only)"""
    # Check if user is admin
    if hasattr(user, 'role') and user.role != 'ADMIN':
        raise HTTPException(
            status_code=403,
            detail="Only administrators can clear cache"
        )
    
    try:
        if cache_type == 'chat':
            cache_manager.chat_cache.clear()
            message = "Chat cache cleared"
        elif cache_type == 'rag':
            cache_manager.rag_cache.clear()
            message = "RAG cache cleared"
        elif cache_type == 'db':
            cache_manager.db_cache.clear()
            message = "Database cache cleared"
        else:
            cache_manager.clear_all()
            message = "All caches cleared"
        
        logger.info("Admin %s cleared %s cache(s)", user.username, cache_type or 'all')
        
        return {
            "success": True,
            "message": message
        }
    except Exception as e:
        logger.error("Error clearing cache: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _get_cache_recommendations(stats: dict) -> list:
    """Generate recommendations based on cache statistics"""
    recommendations = []
    
    # Check chat cache hit rate
    chat_stats = stats.get('chat', {})
    chat_hit_rate = chat_stats.get('hit_rate', 0)
    
    if chat_hit_rate < 30:
        recommendations.append({
            "level": "info",
            "message": f"Low chat cache hit rate ({chat_hit_rate}%). Cache is still warming up or queries are very diverse."
        })
    elif chat_hit_rate > 60:
        recommendations.append({
            "level": "success",
            "message": f"Excellent chat cache hit rate ({chat_hit_rate}%)! Cache is working well."
        })
    
    # Check cache size
    chat_size = chat_stats.get('size', 0)
    chat_max = chat_stats.get('max_size', 500)
    
    if chat_size > chat_max * 0.9:
        recommendations.append({
            "level": "warning",
            "message": f"Chat cache is {chat_size}/{chat_max} items. Consider increasing max_size if hit rate is good."
        })
    
    # Check RAG cache
    rag_stats = stats.get('rag', {})
    rag_hit_rate = rag_stats.get('hit_rate', 0)
    
    if rag_hit_rate > 40:
        recommendations.append({
            "level": "success",
            "message": f"Good RAG cache hit rate ({rag_hit_rate}%). Students are asking similar questions."
        })
    
    if not recommendations:
        recommendations.append({
            "level": "info",
            "message": "Cache is performing normally. Monitor hit rates over time."
        })
    
    return recommendations


# ==================== RAG ENDPOINTS ====================

@app.post("/materials/upload")
async def upload_material(
    file: UploadFile = File(...),
    course_name: str = Form(...),
    course_code: str = Form(...),
    user: UserInDB = Depends(get_current_user)
):
    """Upload course material (PDF, DOCX, TXT) for RAG"""
    # Check if user is admin or teacher
    if user.username == "guest" or (hasattr(user, 'role') and user.role not in ['ADMIN', 'PROFESSOR']):
        raise HTTPException(status_code=403, detail="Only professors and admins can upload materials")
    
    try:
        # Validate file type
        allowed_types = ['.pdf', '.docx', '.doc', '.txt']
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(allowed_types)}")
        
        # Create uploads directory
        upload_dir = Path(__file__).parent / "uploads" / "course_materials"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        timestamp = int(time.time())
        safe_filename = f"{timestamp}_{file.filename}"
        file_path = upload_dir / safe_filename
        
        # Save file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        file_size = len(content)
        
        # Create database entry
        material_id = db_manager.create_course_material(
            filename=safe_filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_type=file_ext[1:],  # Remove dot
            file_size=file_size,
            course_name=course_name,
            course_code=course_code,
            uploaded_by=user.user_id
        )
        
        if not material_id:
            raise HTTPException(status_code=500, detail="Failed to create material entry")
        
        logger.info("Material uploaded: %s by %s", file.filename, user.username)
        
        return {
            "success": True,
            "material_id": material_id,
            "filename": file.filename,
            "file_size": file_size,
            "status": "pending",
            "message": "File uploaded successfully. Processing will begin shortly."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error uploading material: %s", e)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/materials/{material_id}/process")
async def process_material(material_id: int, user: UserInDB = Depends(get_current_user)):
    """Process and index a course material"""
    # Check if user is admin or teacher
    if user.username == "guest" or (hasattr(user, 'role') and user.role not in ['ADMIN', 'PROFESSOR']):
        raise HTTPException(status_code=403, detail="Only professors and admins can process materials")
    
    try:
        # Get material info
        materials = db_manager.get_course_materials()
        material = next((m for m in materials if m['material_id'] == material_id), None)
        
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        
        # Update status to processing
        db_manager.update_material_status(material_id, 'processing')
        
        # Process document
        success, chunk_count, error_msg = rag_service.process_document(
            material_id=material_id,
            file_path=material['file_path'],
            file_type=material['file_type'],
            course_code=material['course_code']
        )
        
        if success:
            # Update status to ready
            db_manager.update_material_status(material_id, 'ready', chunk_count)
            logger.info("Material %s processed: %s chunks", material_id, chunk_count)
            
            return {
                "success": True,
                "material_id": material_id,
                "chunk_count": chunk_count,
                "status": "ready",
                "message": f"Material processed successfully. {chunk_count} chunks indexed."
            }
        else:
            # Update status to error
            db_manager.update_material_status(material_id, 'error')
            raise HTTPException(status_code=500, detail=error_msg)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing material: %s", e)
        db_manager.update_material_status(material_id, 'error')
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get("/materials")
async def get_materials(
    course_code: Optional[str] = None,
    user: UserInDB = Depends(get_current_user)
):
    """Get list of course materials"""
    try:
        # Professors/admins see all, students see only ready materials
        materials = db_manager.get_course_materials(course_code=course_code)
        
        # Filter for students (only show ready materials)
        if user.username != "guest" and hasattr(user, 'role') and user.role == 'STUDENT':
            materials = [m for m in materials if m['status'] == 'ready']
        
        return {
            "success": True,
            "materials": materials,
            "count": len(materials)
        }
    except Exception as e:
        logger.error("Error getting materials: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get materials")


@app.get("/materials/{material_id}")
async def get_material(material_id: int, user: UserInDB = Depends(get_current_user)):
    """Get specific material details"""
    try:
        materials = db_manager.get_course_materials()
        material = next((m for m in materials if m['material_id'] == material_id), None)
        
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        
        # Get chunks if processed
        chunks = []
        if material['processed']:
            chunks = db_manager.get_document_chunks(material_id)
        
        return {
            "success": True,
            "material": material,
            "chunks": chunks,
            "chunk_count": len(chunks)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting material: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get material")


@app.delete("/materials/{material_id}")
async def delete_material(material_id: int, user: UserInDB = Depends(get_current_user)):
    """Delete a course material"""
    # Check if user is admin or teacher
    if user.username == "guest" or (hasattr(user, 'role') and user.role not in ['ADMIN', 'PROFESSOR']):
        raise HTTPException(status_code=403, detail="Only professors and admins can delete materials")
    
    try:
        # Get material info
        materials = db_manager.get_course_materials()
        material = next((m for m in materials if m['material_id'] == material_id), None)
        
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        
        # Delete from vector DB
        rag_service.delete_material(material_id)
        
        # Delete file
        try:
            file_path = Path(material['file_path'])
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.warning("Could not delete file: %s", e)
        
        # Delete from database
        db_manager.delete_course_material(material_id)
        
        logger.info("Material %s deleted by %s", material_id, user.username)
        
        return {
            "success": True,
            "message": "Material deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting material: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete material")


@app.get("/materials/search")
async def search_materials(
    query: str,
    course_code: Optional[str] = None,
    top_k: int = 5,
    user: UserInDB = Depends(get_current_user)
):
    """Search course materials using semantic search"""
    try:
        # Search using RAG service
        results = rag_service.search(query, course_code, top_k)
        
        # Log query for analytics
        if user.username != "guest" and hasattr(user, 'user_id'):
            db_manager.log_rag_query(
                user_id=user.user_id,
                query_text=query,
                course_code=course_code or "all",
                chunks_retrieved=len(results),
                response_generated=len(results) > 0
            )
        
        return {
            "success": True,
            "query": query,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error("Error searching materials: %s", e)
        raise HTTPException(status_code=500, detail="Search failed")


@app.get("/rag/stats")
async def get_rag_stats(user: UserInDB = Depends(get_current_user)):
    """Get RAG system statistics"""
    try:
        # Get all materials
        materials = db_manager.get_course_materials()
        
        total_materials = len(materials)
        ready_materials = len([m for m in materials if m.get("status") == "ready"])
        processing_materials = len([m for m in materials if m.get("status") == "processing"])
        pending_materials = len([m for m in materials if m.get("status") == "pending"])
        error_materials = len([m for m in materials if m.get("status") == "error"])
        total_chunks = sum(m.get("chunk_count", 0) for m in materials if m.get("chunk_count"))
        
        return {
            "success": True,
            "total_materials": total_materials,
            "ready_materials": ready_materials,
            "processing_materials": processing_materials,
            "pending_materials": pending_materials,
            "error_materials": error_materials,
            "total_chunks": total_chunks
        }
    except Exception as e:
        logger.error("Error getting RAG stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get RAG stats")


@app.get("/materials/health")
async def get_materials_health(user: UserInDB = Depends(get_current_user)):
    """Check health of materials system components"""
    try:
        health_status = {
            "database": False,
            "vector_db": False,
            "upload_directory": False,
            "rag_service": False
        }
        
        # Check database connection
        try:
            materials = db_manager.get_course_materials()
            health_status["database"] = True
        except Exception as e:
            logger.error("Database health check failed: %s", e)
        
        # Check upload directory
        try:
            upload_dir = Path(__file__).parent / "uploads" / "course_materials"
            upload_dir.mkdir(parents=True, exist_ok=True)
            health_status["upload_directory"] = upload_dir.exists() and upload_dir.is_dir()
        except Exception as e:
            logger.error("Upload directory health check failed: %s", e)
        
        # Check RAG service
        try:
            rag_stats = rag_service.get_stats()
            health_status["rag_service"] = True
            health_status["vector_db"] = True
        except Exception as e:
            logger.error("RAG service health check failed: %s", e)
        
        overall_health = all(health_status.values())
        
        return {
            "success": True,
            "healthy": overall_health,
            "components": health_status,
            "timestamp": int(time.time())
        }
    except Exception as e:
        logger.error("Error checking materials health: %s", e)
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/courses")
async def get_courses(user: UserInDB = Depends(get_current_user)):
    """Get list of courses"""
    try:
        # Professors see their courses, admins see all
        instructor_id = None
        if hasattr(user, 'role') and user.role == 'PROFESSOR':
            instructor_id = user.user_id
        
        courses = db_manager.get_courses(instructor_id=instructor_id)
        
        return {
            "success": True,
            "courses": courses,
            "count": len(courses)
        }
    except Exception as e:
        logger.error("Error getting courses: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get courses")


@app.post("/courses")
async def create_course(
    course_code: str = Form(...),
    course_name: str = Form(...),
    description: str = Form(""),
    user: UserInDB = Depends(get_current_user)
):
    """Create a new course"""
    # Check if user is admin or teacher
    if user.username == "guest" or (hasattr(user, 'role') and user.role not in ['ADMIN', 'PROFESSOR']):
        raise HTTPException(status_code=403, detail="Only professors and admins can create courses")
    
    try:
        course_id = db_manager.create_course(
            course_code=course_code,
            course_name=course_name,
            description=description,
            instructor_id=user.user_id
        )
        
        if not course_id:
            raise HTTPException(status_code=500, detail="Failed to create course")
        
        logger.info("Course created: %s by %s", course_code, user.username)
        
        return {
            "success": True,
            "course_id": course_id,
            "course_code": course_code,
            "message": "Course created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating course: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create course: {str(e)}")




# ==================== ADMIN TOKEN MANAGEMENT ENDPOINTS ====================

@app.post("/admin/update-all-token-limits")
async def update_all_token_limits(request: dict):
    """Update all users' token limits (called by admin panel)"""
    try:
        max_tokens = request.get("max_tokens")
        if not max_tokens or not isinstance(max_tokens, int) or max_tokens < 1:
            raise HTTPException(status_code=400, detail="Invalid max_tokens value")
        
        # Update all user token limits in database
        success = db_manager.update_all_user_token_limits(max_tokens)
        
        if success:
            logger.info("Updated all user token limits to %s", max_tokens)
            return {
                "success": True,
                "message": f"Updated all user token limits to {max_tokens}",
                "max_tokens": max_tokens
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update user token limits")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating all token limits: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to update token limits: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

