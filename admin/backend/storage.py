import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

_lock = threading.Lock()


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _read_json(name: str, default):
    p = _path(name)
    if not os.path.exists(p):
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(name: str, data) -> None:
    tmp = _path(name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(name))


# -------- Users --------

def list_users() -> List[Dict[str, Any]]:
    return _read_json("users.json", [])


def search_users(q: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    users = list_users()
    
    # Apply search filter
    if q:
        ql = q.lower()
        users = [u for u in users if ql in u.get("username", "").lower() or ql in u.get("email", "").lower()]
    
    # Apply role filter
    if role:
        users = [u for u in users if u.get("role", "").upper() == role.upper()]
    
    # Apply status filter — exact match against status field
    if status:
        status_upper = status.upper()
        users = [u for u in users if u.get("status", "").upper() == status_upper]
    
    return users


def add_user(username: str, email: str, role: str = "user") -> Dict[str, Any]:
    with _lock:
        users = list_users()
        now = time.time()
        rec = {
            "id": str(uuid.uuid4()),
            "username": username,
            "email": email,
            "role": role,
            "status": "active",
            "active": True,
            "created_at": now,
            "last_login": None,
        }
        users.append(rec)
        _write_json("users.json", users)
        return rec


def update_user(user_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Fields that callers must not overwrite
    _PROTECTED = {"id", "created_at"}
    with _lock:
        users = list_users()
        found = None
        for u in users:
            if u.get("id") == user_id:
                for k, v in patch.items():
                    if k in _PROTECTED or v is None:
                        continue
                    u[k] = v
                # keep active in sync with status
                if "status" in patch and patch["status"] is not None:
                    u["active"] = (str(u.get("status") or "").lower() == "active")
                found = u
                break
        if found is None:
            return None
        _write_json("users.json", users)
        return found


def delete_user(user_id: str) -> bool:
    """Delete a user by id from JSON store. Returns True if deleted."""
    with _lock:
        users = list_users()
        new_users: List[Dict[str, Any]] = []
        deleted = False
        for u in users:
            if u.get("id") == user_id:
                deleted = True
                continue
            new_users.append(u)
        if not deleted:
            return False
        _write_json("users.json", new_users)
        return True


# -------- Audit --------

def list_audit() -> List[Dict[str, Any]]:
    return _read_json("audit.json", [])


def add_audit(actor: str, action: str, target_type: Optional[str], target_id: Optional[str], meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    with _lock:
        logs = list_audit()
        rec = {
            "id": str(uuid.uuid4()),
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "meta": meta,
            "ts": time.time(),
        }
        logs.append(rec)
        _write_json("audit.json", logs)
        return rec


# -------- Settings --------

def get_settings() -> Dict[str, Any]:
    data = _read_json("settings.json", {})
    if "tokenization_limit" not in data:
        data["tokenization_limit"] = 350
    return data


def set_tokenization_limit(limit: int) -> int:
    with _lock:
        data = get_settings()
        data["tokenization_limit"] = int(max(1, limit))
        _write_json("settings.json", data)
        return data["tokenization_limit"]


# -------- Files --------

def list_files() -> List[Dict[str, Any]]:
    return _read_json("files.json", [])


def add_file(user_id: str, file_name: str, file_type: str = "unknown") -> Dict[str, Any]:
    with _lock:
        files = list_files()
        now = time.time()
        rec = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "file_name": file_name,
            "file_type": file_type,
            "status": "validated",
            "created_at": now,
        }
        files.append(rec)
        _write_json("files.json", files)
        return rec


def delete_file(file_id: str) -> bool:
    """Delete a file by id from JSON store. Returns True if deleted, False if not found."""
    with _lock:
        files = list_files()
        new_files = [f for f in files if f.get("id") != file_id]
        if len(new_files) == len(files):
            return False
        _write_json("files.json", new_files)
        return True


# -------- Flags --------

def list_flags() -> List[Dict[str, Any]]:
    return _read_json("flags.json", [])


def add_flag(target_type: str, target_id: str, reason: str) -> Dict[str, Any]:
    with _lock:
        flags = list_flags()
        now = time.time()
        rec = {
            "id": str(uuid.uuid4()),
            "target_type": target_type,
            "target_id": target_id,
            "reason": reason,
            "status": "new",
            "created_at": now,
        }
        flags.append(rec)
        _write_json("flags.json", flags)
        return rec


def update_flag(flag_id: str, status: str) -> Optional[Dict[str, Any]]:
    with _lock:
        flags = list_flags()
        found = None
        for f in flags:
            if f.get("id") == flag_id:
                f["status"] = status
                found = f
                break
        if found is None:
            return None
        _write_json("flags.json", flags)
        return found


