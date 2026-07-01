"""
FAIA System Auto Test
Tests all modules and endpoints, prints PASS/FAIL for each.
Run with: python test_system.py
Servers must be running first.
"""

import requests
import json
import time
import os

BACKEND = "http://localhost:8000"
WEB = "http://localhost:8080"
ADMIN = "http://localhost:8001"

# Test credentials — set these via environment variables or update for your deployment
# Example: set TEST_STUDENT_USER=yourstudent before running
STUDENT_USER = os.getenv("TEST_STUDENT_USER", "student")
STUDENT_PASS = os.getenv("TEST_STUDENT_PASS", "Student@1234")
PROF_USER = os.getenv("TEST_PROF_USER", "professor")
PROF_PASS = os.getenv("TEST_PROF_PASS", "Prof@1234")
ADMIN_USER = os.getenv("TEST_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("TEST_ADMIN_PASS", "Admin@1234")

results = []
timings = []

def test(name, passed, detail="", elapsed=None):
    status = "PASS" if passed else "FAIL"
    time_str = f" ({elapsed}s)" if elapsed is not None else ""
    results.append((name, status, detail, elapsed))
    print(f"  [{status}]{time_str} {name}" + (f" — {detail}" if detail else ""))

def timed_chat(token, prompt, use_rag=False, chat_id=None, timeout=120):
    """Send chat request and return (data, elapsed_seconds)"""
    body = {"prompt": prompt, "model": "qwen", "use_rag": use_rag}
    if chat_id:
        body["chat_id"] = str(chat_id)
    start = time.time()
    r = requests.post(f"{WEB}/chat", json=body,
        headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    elapsed = round(time.time() - start, 1)
    return r.json(), elapsed

def get_token(username, password):
    try:
        r = requests.post(f"{WEB}/token", data={"username": username, "password": password}, timeout=10)
        data = r.json()
        return data.get("access_token")
    except:
        return None

def auth_header(token):
    return {"Authorization": f"Bearer {token}"}

total_start = time.time()

print("\n" + "="*60)
print("  FAIA SYSTEM AUTO TEST")
print("="*60)

# ── MODULE 1: HEALTH CHECKS ──────────────────────────────────
print("\n[1] Health Checks")
try:
    r = requests.get(f"{BACKEND}/health", timeout=5)
    test("Backend running (port 8000)", r.status_code == 200)
except:
    test("Backend running (port 8000)", False, "Connection refused")

try:
    r = requests.get(f"{WEB}/health", timeout=5)
    test("Web server running (port 8080)", r.status_code == 200)
except:
    test("Web server running (port 8080)", False, "Connection refused")

try:
    r = requests.get(f"{ADMIN}/admin/health", timeout=5)
    test("Admin backend running (port 8001)", r.status_code == 200)
except:
    test("Admin backend running (port 8001)", False, "Connection refused")

# ── MODULE 2: AUTHENTICATION ─────────────────────────────────
print("\n[2] Authentication Module")

student_token = get_token(STUDENT_USER, STUDENT_PASS)
test("Student login", student_token is not None, f"user: {STUDENT_USER}")

prof_token = get_token(PROF_USER, PROF_PASS)
test("Professor login", prof_token is not None, f"user: {PROF_USER}")

admin_token = get_token(ADMIN_USER, ADMIN_PASS)
test("Admin login (web)", admin_token is not None, f"user: {ADMIN_USER}")

try:
    r = requests.post(f"{ADMIN}/admin/login",
        data={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=10)
    data = r.json()
    admin_panel_token = data.get("access_token")
    test("Admin panel login (port 8001)", admin_panel_token is not None)
except Exception as e:
    admin_panel_token = None
    test("Admin panel login (port 8001)", False, str(e))

try:
    r = requests.get(f"{WEB}/", timeout=5)
    test("Guest mode (no login)", r.status_code == 200)
except:
    test("Guest mode (no login)", False)

import random
test_username = f"autotest_{random.randint(1000,9999)}"
try:
    r = requests.post(f"{WEB}/register", data={
        "username": test_username,
        "password": "Test1234!",
        "email": f"{test_username}@test.com"
    }, timeout=10)
    data = r.json()
    test("Register new user", data.get("success") or data.get("access_token"), f"user: {test_username}")
except Exception as e:
    test("Register new user", False, str(e))

# ── MODULE 3: CHAT (AI RESPONSE) ─────────────────────────────
print("\n[3] Academic Assistance Module (Chat)")

if student_token:
    try:
        # Turn 1 - introduce name
        d1, t1 = timed_chat(student_token, "My name is TestUser123. Remember that.")
        chat_id = d1.get("chat_id")
        test("AI chat - turn 1 (no RAG)", bool(d1.get("response")), f"chat_id={chat_id}", t1)

        # Turn 2 - recall name (context test)
        d2, t2 = timed_chat(student_token, "What is my name?", chat_id=chat_id)
        response_text = d2.get("response", "").lower()
        remembers = "testuser123" in response_text or "testuser" in response_text
        test("AI remembers context (turn 2)", remembers, d2.get("response","")[:80], t2)

        # Turn 3 - RAG query
        d3, t3 = timed_chat(student_token, "What courses are available in the system?", use_rag=True, timeout=180)
        test("AI chat - RAG query (turn 3)", bool(d3.get("response")), d3.get("response","")[:80], t3)

    except Exception as e:
        test("AI chat - turn 1 (no RAG)", False, str(e))
        test("AI remembers context (turn 2)", False, str(e))
        test("AI chat - RAG query (turn 3)", False, str(e))
else:
    test("AI chat - turn 1 (no RAG)", False, "No student token")
    test("AI remembers context (turn 2)", False, "No student token")
    test("AI chat - RAG query (turn 3)", False, "No student token")

# ── MODULE 4: CONTEXT RETENTION ──────────────────────────────
print("\n[4] Context Retention Module")

if student_token:
    try:
        r = requests.get(f"{WEB}/chat/history",
            headers=auth_header(student_token), timeout=10)
        data = r.json()
        has_history = "history" in data or isinstance(data, list)
        history_list = data.get("history", data) if isinstance(data, dict) else data
        has_content = isinstance(history_list, list) and len(history_list) > 0
        test("Chat history loads", has_history)
        test("Chat history has content", has_content, f"{len(history_list)} chats found")
    except Exception as e:
        test("Chat history loads", False, str(e))
        test("Chat history has content", False, str(e))
else:
    test("Chat history loads", False, "No student token")
    test("Chat history has content", False, "No student token")

# ── MODULE 5: PROFESSOR SUPPORT (FILE UPLOAD) ────────────────
print("\n[5] Professor Support Module")

if prof_token:
    try:
        test_content = b"FAIA Test Document\nPython is a programming language."
        r = requests.post(f"{WEB}/upload",
            files={"file": ("test.txt", test_content, "text/plain")},
            data={"session_id": "test_session"},
            headers=auth_header(prof_token),
            timeout=30)
        data = r.json()
        test("File upload", data.get("success") or data.get("file_id"))
    except Exception as e:
        test("File upload", False, str(e))
else:
    test("File upload", False, "No professor token")

# ── MODULE 6: ADMIN MANAGEMENT ───────────────────────────────
print("\n[6] Admin Management Module")

if admin_panel_token:
    try:
        r = requests.get(f"{ADMIN}/admin/users",
            headers=auth_header(admin_panel_token), timeout=10)
        data = r.json()
        test("Admin: list users", isinstance(data, list) and len(data) > 0, f"{len(data)} users")
    except Exception as e:
        test("Admin: list users", False, str(e))

    try:
        r = requests.get(f"{ADMIN}/admin/sessions",
            headers=auth_header(admin_panel_token), timeout=10)
        test("Admin: list sessions", r.status_code == 200)
    except Exception as e:
        test("Admin: list sessions", False, str(e))

    try:
        r = requests.get(f"{ADMIN}/admin/audit",
            headers=auth_header(admin_panel_token), timeout=10)
        test("Admin: audit log", r.status_code == 200)
    except Exception as e:
        test("Admin: audit log", False, str(e))

    try:
        r = requests.get(f"{ADMIN}/admin/password-resets",
            headers=auth_header(admin_panel_token), timeout=10)
        test("Admin: pending resets endpoint", r.status_code == 200)
    except Exception as e:
        test("Admin: pending resets endpoint", False, str(e))

    try:
        r = requests.get(f"{ADMIN}/admin/materials",
            headers=auth_header(admin_panel_token), timeout=10)
        test("Admin: materials list", r.status_code == 200)
    except Exception as e:
        test("Admin: materials list", False, str(e))

    try:
        r = requests.get(f"{ADMIN}/admin/overview",
            headers=auth_header(admin_panel_token), timeout=10)
        test("Admin: dashboard overview", r.status_code == 200)
    except Exception as e:
        test("Admin: dashboard overview", False, str(e))

    try:
        r = requests.get(f"{ADMIN}/admin/tokens/limits",
            headers=auth_header(admin_panel_token), timeout=10)
        test("Admin: token limits", r.status_code == 200)
    except Exception as e:
        test("Admin: token limits", False, str(e))
else:
    test("Admin: list users", False, "No admin panel token")
    test("Admin: list sessions", False, "No admin panel token")
    test("Admin: audit log", False, "No admin panel token")

# ── FORGOT PASSWORD ───────────────────────────────────────────
print("\n[7] Forgot Password Flow")
try:
    r = requests.post(f"{BACKEND}/forgot-password",
        json={"email": os.getenv("TEST_ADMIN_EMAIL", "admin@faia.local")}, timeout=10)
    data = r.json()
    test("Forgot password request", data.get("success"), str(data.get("message","")))
except Exception as e:
    test("Forgot password request", False, str(e))

# ── TOKEN USAGE ───────────────────────────────────────────────
print("\n[8] Token Tracking")
if student_token:
    try:
        r = requests.get(f"{WEB}/user/tokens",
            headers=auth_header(student_token), timeout=10)
        data = r.json()
        test("Token usage endpoint", data.get("success") or "used_tokens" in str(data))
    except Exception as e:
        test("Token usage endpoint", False, str(e))

# ── SUMMARY ───────────────────────────────────────────────────
total_elapsed = round(time.time() - total_start, 1)
print("\n" + "="*60)
passed = sum(1 for _, s, _, _ in results if s == "PASS")
failed = sum(1 for _, s, _, _ in results if s == "FAIL")
total = len(results)
print(f"  RESULTS: {passed}/{total} passed  |  {failed} failed  |  total time: {total_elapsed}s")

# Show AI response times
ai_tests = [(n, e) for n, s, _, e in results if e is not None]
if ai_tests:
    print("\n  AI RESPONSE TIMES:")
    for name, elapsed in ai_tests:
        print(f"    {elapsed}s — {name}")

if failed > 0:
    print("\n  FAILED TESTS:")
    for name, status, detail, _ in results:
        if status == "FAIL":
            print(f"    - {name}" + (f": {detail}" if detail else ""))
print("="*60 + "\n")


