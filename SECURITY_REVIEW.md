# FAIA Security & Code Review Log

Two independent AI reviews were conducted on the public repository (Kimi and GitHub Copilot).
This document tracks every issue raised, its status, and what was done.

---

## Review Sources
- **Kimi** — reviewed via URL fetch after repo was made public
- **GitHub Copilot** — reviewed via IDE after repo was made public

---

## Issues & Status

### 🔴 CRITICAL — Fixed

| # | Issue | File | Fix | Commit |
|---|---|---|---|---|
| C1 | Hardcoded admin credentials with predictable salt (`faia0000`) in SQL schema | `backend/database/faia_chat_system.sql` | Removed INSERT, replaced with setup instructions | `f51e90f` |
| C2 | CORS wildcard (`*`) with `allow_credentials=True` — allows CSRF credential theft | `backend/services/backend_service.py`, `admin/backend/main.py` | Changed defaults to `localhost:8080` and `localhost:8090` — overridable via env vars | `f51e90f` |
| C3 | Real test credentials hardcoded in public repo (`kiro/123456`, `akino/Admin123@`) | `test_system.py` | Replaced with `os.getenv()` calls with placeholder defaults | `a188bd1` |
| C4 | Student ID `202003039` in README, config prompts, and public-facing text | `README.md`, `faia_config.json` | Removed from all files | `eaa7e90` |

---

### 🟠 HIGH — Fixed

| # | Issue | File | Fix | Commit |
|---|---|---|---|---|
| H1 | Hardcoded Windows path `D:/phi2` in `.gitignore` | `.gitignore` | Removed, replaced with generic `*.pt`, `*.bin`, `*.pth` patterns | `a188bd1` |
| H2 | Personal machine path `D:\AI_Models\qwen-model` in `.env.example` | `.env.example` | Changed to generic `./models/qwen` | `a188bd1` |
| H3 | SQL trigger token counting bug — `period_end > CURRENT_TIMESTAMP` fails when period_end is NULL | `faia_chat_system.sql` | Changed to `(period_end IS NULL OR period_end > CURRENT_TIMESTAMP)` | `a188bd1` |
| H4 | README stated "bcrypt hashed passwords" but code uses SHA256 | `README.md` | Corrected to "SHA256 with random salts" | `a188bd1` |

---

### 🟠 HIGH — Acknowledged, Not Fixed (graduation project scope)

| # | Issue | Reason |
|---|---|---|
| A1 | SHA256 used for password hashing instead of bcrypt/Argon2 | SHA256+salt is not production-grade but acceptable for a local university tool. bcrypt is in requirements but would require migrating all existing password hashes. Noted as known limitation. |
| A2 | In-memory JWT token blacklist (lost on restart) | Acceptable for local deployment. Would need Redis or DB table for production. Noted as known limitation. |
| A3 | Rate limiting disabled in faia_config.json | The config flag exists but the middleware isn't wired to use it. Acceptable for graduation. |
| A4 | FP16 on CPU in model_service.py | Only affects local HuggingFace provider (not Ollama). The `MODEL_PROVIDER=ollama` path (recommended) never touches this code. |

---

### 🟡 MEDIUM — Fixed

| # | Issue | File | Fix | Commit |
|---|---|---|---|---|
| M1 | psutil version 5.9.8 (from 2018, outdated) | `requirements.txt` | Updated to 6.1.0 | `a188bd1` |
| M2 | transformers version 4.57.1 incompatible with huggingface-hub 1.x | `requirements.txt` | Upgraded to 5.12.1 during testing session | `357fff0` |
| M3 | Jinja2 3.1.6 incompatible with Starlette 1.3.x (`TemplateResponse` signature change) | `faia-web/web_server.py` | Updated call signature to new API, pinned Jinja2==3.1.4 in requirements | `357fff0` |

---

### 🟡 MEDIUM — Not Fixed (style/preference)

| # | Issue | Reason |
|---|---|---|
| N1 | Inconsistent string formatting (% vs f-strings) | Style preference, not a bug. No behavior change. |
| N2 | Duplicated text extraction methods in rag_service.py | Refactor would be nice but introduces risk of breaking working code. |
| N3 | Broad `except Exception` catches in several places | Would require testing each specific exception type. Low priority. |
| N4 | Hardcoded defaults in model_service.py (Ollama URL, model name) | Already overridable via env vars which is the right pattern. |
| N5 | No conversation history size limit | The backend already limits context via `STUDENT_MAX_HISTORY_TURNS` constant. |
| N6 | Provider validation silently falls back to local | Acceptable behavior — wrong env var = falls back gracefully rather than crashing. |

---

### ❌ Flagged by Reviewers but Incorrect

| # | Claim | Reality |
|---|---|---|
| X1 | "CORS in faia_config.json lines 334-339" | faia_config.json has no CORS section. Copilot confused it with backend_service.py middleware. |
| X2 | "Truncated prompts with [...]" in faia_config.json | The [...] was Copilot's own truncation while fetching the file. The actual prompts are complete. |
| X3 | "Notifications disabled but auto-actions enabled is a bug" | This is intentional — notifications are email-based (not implemented). The flags control different behavior. |
| X4 | "embed_text_from_excel() is dead code" | Excel files are supported in the upload endpoint. Not dead code. |

---

## What's Still Open (Future Work)

These are real issues but out of scope for graduation submission:

1. **Replace SHA256 with bcrypt** — requires DB migration of all password hashes
2. **Persistent token blacklist** — needs Redis or a `revoked_tokens` DB table
3. **Rate limiting middleware** — needs to wire the config flag to actual FastAPI middleware
4. **Embedding batch processing** — add `batch_size=32` to sentence-transformers encode calls
5. **ChromaDB null guard in rag_service** — add `if self.collection is None: raise` before operations

---

## Commit Reference

| Commit | Summary |
|---|---|
| `357fff0` | Fix Ollama provider guard, Starlette TemplateResponse, web timeout, file attachment card, bot bubble gap |
| `eaa7e90` | Remove student ID from all public-facing files |
| `f51e90f` | Remove hardcoded admin credentials, fix CORS wildcard defaults |
| `a188bd1` | Remove test credentials, fix SQL trigger NULL bug, clean paths, update psutil |
