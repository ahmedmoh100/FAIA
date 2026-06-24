import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

web_app = FastAPI(title="FAIA Web Interface", version="1.0.0")

# CORS — restrict origins via env var in production
# Example: CORS_ORIGINS=https://yourapp.com,https://api.yourapp.com
_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

# Backend API URL
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Default request timeout — (connect_timeout, read_timeout) in seconds
# RAG queries can take longer due to context building, so read timeout is generous
_TIMEOUT = (3, 120)


@web_app.get("/static/js/{filename}")
async def serve_js(filename: str):
    """Serve JavaScript files with no-cache headers.
    Path is validated to prevent directory traversal attacks.
    """
    # Resolve and confirm the file is strictly under static_dir/js/
    base = Path(static_dir).resolve() / "js"
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    response = FileResponse(str(candidate), media_type="application/javascript")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


web_app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


@web_app.get("/health")
async def health_check():
    """Health check for the web interface."""
    backend_healthy = True
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=5)
        backend_healthy = r.status_code == 200
    except Exception:
        backend_healthy = False

    return {
        "status": "healthy" if backend_healthy else "warning",
        "service": "FAIA Web Interface",
        "version": "1.0.0",
        "backend_connection": backend_healthy,
        "static_files": os.path.exists(static_dir),
        "templates": os.path.exists(templates_dir),
    }


@web_app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Main chat interface page."""
    response = templates.TemplateResponse(request, "chat.html", {"timestamp": int(time.time())})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@web_app.get("/login")
async def login_page_redirect():
    return RedirectResponse(url="/")


@web_app.get("/register")
async def register_page_redirect():
    return RedirectResponse(url="/")


@web_app.post("/register")
async def register_user(
    username: str = Form(...),
    password: str = Form(...),
    email: Optional[str] = Form(None),
):
    """Forward registration to backend."""
    try:
        r = requests.post(
            f"{BACKEND_URL}/register",
            data={"username": username, "password": password, "email": email},
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            return {"success": True, "access_token": data.get("access_token"), "action": "registered"}
        try:
            msg = r.json().get("detail", f"Registration failed: {r.status_code}")
        except Exception:
            msg = f"Registration failed: {r.status_code}"
        raise HTTPException(status_code=r.status_code, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")


@web_app.post("/token")
async def login_user(username: str = Form(...), password: str = Form(...)):
    """Forward login to backend."""
    try:
        r = requests.post(
            f"{BACKEND_URL}/token",
            data={"username": username, "password": password},
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            return {"success": True, "access_token": data.get("access_token"),
                    "session_id": data.get("session_id"), "action": "logged_in"}
        try:
            msg = r.json().get("detail", f"Login failed: {r.status_code}")
        except Exception:
            msg = f"Login failed: {r.status_code}"
        raise HTTPException(status_code=r.status_code, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")


@web_app.post("/chat")
async def chat_proxy(request: Request):
    """Proxy chat to backend."""
    try:
        body = await request.json()
        auth_header = request.headers.get("Authorization", "")
        r = requests.post(f"{BACKEND_URL}/chat", json=body,
                          headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        data = r.json()
        if r.status_code == 429:
            return {"success": False, "error": data.get("detail", "Token limit reached"), "code": 429}
        if r.status_code >= 400:
            return {"success": False, "error": data.get("detail", f"Error {r.status_code}"), "code": r.status_code}
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")


@web_app.get("/chat/history")
async def chat_history_proxy(request: Request):
    try:
        auth_header = request.headers.get("Authorization", "")
        r = requests.get(f"{BACKEND_URL}/chat/history",
                         headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        return r.json()
    except Exception:
        return {"history": []}


@web_app.delete("/chat/history")
async def delete_chat_history_proxy(request: Request):
    try:
        auth_header = request.headers.get("Authorization", "")
        r = requests.delete(f"{BACKEND_URL}/chat/history",
                            headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.delete("/chat/{chat_id}")
async def delete_chat_proxy(chat_id: int, request: Request):
    try:
        auth_header = request.headers.get("Authorization", "")
        r = requests.delete(f"{BACKEND_URL}/chat/{chat_id}",
                            headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.post("/logout")
async def logout_proxy(request: Request):
    try:
        auth_header = request.headers.get("Authorization", "")
        r = requests.post(f"{BACKEND_URL}/logout",
                          headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        return r.json()
    except Exception:
        return {"success": False}


@web_app.post("/change-password")
async def change_password_proxy(request: Request):
    try:
        body = await request.json()
        auth_header = request.headers.get("Authorization", "")
        r = requests.post(f"{BACKEND_URL}/change-password", json=body,
                          headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.get("/materials")
async def materials_proxy(request: Request):
    try:
        auth_header = request.headers.get("Authorization", "")
        r = requests.get(f"{BACKEND_URL}/materials",
                         headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        return r.json()
    except Exception:
        return {"materials": []}


@web_app.post("/upload")
async def upload_proxy(request: Request):
    try:
        form = await request.form()
        if "file" not in form:
            raise HTTPException(status_code=400, detail="No file provided")
        auth_header = request.headers.get("Authorization", "")
        r = requests.post(
            f"{BACKEND_URL}/upload",
            files={"file": (form["file"].filename, form["file"].file, form["file"].content_type)},
            data={k: v for k, v in form.items() if k != "file"},
            headers={"Authorization": auth_header},
            timeout=(3, 60),  # uploads may take longer
        )
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.post("/forgot-password")
async def forgot_password_proxy(request: Request):
    try:
        body = await request.json()
        r = requests.post(f"{BACKEND_URL}/forgot-password", json=body, timeout=_TIMEOUT)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.post("/reset-password")
async def reset_password_proxy(request: Request):
    try:
        body = await request.json()
        r = requests.post(f"{BACKEND_URL}/reset-password", json=body, timeout=_TIMEOUT)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.post("/feedback")
async def feedback_proxy(request: Request):
    try:
        body = await request.json()
        auth_header = request.headers.get("Authorization", "")
        r = requests.post(f"{BACKEND_URL}/feedback", json=body,
                          headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.post("/report")
async def report_proxy():
    return {"success": True, "message": "Report received"}


@web_app.get("/user/tokens")
async def web_get_user_tokens(request: Request):
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return {"success": False, "error": "Authentication required", "code": 401}
        r = requests.get(f"{BACKEND_URL}/user/tokens",
                         headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        try:
            msg = r.json().get("detail", f"Backend error: {r.status_code}")
        except Exception:
            msg = f"Backend error: {r.status_code}"
        return {"success": False, "error": msg, "code": r.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


@web_app.get("/user/files")
async def web_get_user_files(request: Request):
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return {"success": False, "error": "Authentication required", "code": 401}
        r = requests.get(f"{BACKEND_URL}/user/files",
                         headers={"Authorization": auth_header}, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        try:
            msg = r.json().get("detail", f"Backend error: {r.status_code}")
        except Exception:
            msg = f"Backend error: {r.status_code}"
        return {"success": False, "error": msg, "code": r.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting FAIA Web Interface on http://0.0.0.0:8080 (backend: %s)", BACKEND_URL)
    uvicorn.run("web_server:web_app", host="0.0.0.0", port=8080, reload=True)
