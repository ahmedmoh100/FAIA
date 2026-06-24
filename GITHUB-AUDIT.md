
---

## 12. Multi-Provider Model Support � 2026-06-23
Priority: (1) Local HuggingFace (default/original) (2) Ollama (3) OpenAI. Implementing now to enable testing with qwen2.5:1.5b already in Ollama. Scope: backend_service.py generate_response() + .env.example + README. No changes to auth/RAG/sessions/admin.

| 70 | 2026-06-23 | 18:22 | EDIT | backend/services/model_service.py | Added multi-provider support: generate_response() now routes to _generate_ollama(), _generate_openai(), or _generate_local() based on MODEL_PROVIDER env var. Ollama and OpenAI added as optional providers. Local HuggingFace remains default. |
| 71 | 2026-06-23 | 18:22 | EDIT | .env.example | Added MODEL_PROVIDER, OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL |
| 72 | 2026-06-23 | 18:22 | EDIT | README.md | Model setup section rewritten with all 3 options (Ollama, local HuggingFace, OpenAI) with exact commands |
| 73 | 2026-06-23 | 18:22 | RENAME | backend/services/backend_phi2_service.py ? backend_service.py | Old phi2 name removed. start_all.bat updated. |
| 74 | 2026-06-23 | 18:22 | MOVE | admin/db/faia_chat_system.sql ? backend/database/faia_chat_system.sql | SQL lives next to database_integration.py |
| 75 | 2026-06-23 | 18:22 | DELETE | uploads/ test files | study_material_ and personal docx files removed again (came back via copy) |

## 13. Testing & Runtime Compatibility Hardening — 2026-06-24
Priority: make the app start and pass a lightweight smoke test using the Ollama/Qwen path without failing on optional local-model or RAG dependency issues. Scope: model_service.py, rag_service.py, backend_service.py, .env.example.

| 76 | 2026-06-24 | 13:20 | EDIT | backend/services/model_service.py | Made local Transformers imports lazy so Ollama mode no longer crashes on import-time Hugging Face dependency mismatches. Added conditional model-path validation so local Qwen path is only required when local provider mode is used. |
| 77 | 2026-06-24 | 13:25 | EDIT | backend/services/rag_service.py | Made ChromaDB and sentence-transformers imports optional/fallback so the backend can start even if the heavier RAG stack is unavailable. |
| 78 | 2026-06-24 | 13:27 | EDIT | backend/services/backend_service.py | Made RAG integration optional for smoke testing by using a stub when RAG is disabled or its dependencies fail. |
| 79 | 2026-06-24 | 13:30 | EDIT | .env.example | Added LOAD_QWEN and ENABLE_RAG settings so developers can explicitly choose local-model loading and whether to enable the heavier RAG stack. |
| 80 | 2026-06-24 | 13:35 | TEST | local runtime | Started Ollama locally, pulled qwen2.5:1.5b, and attempted backend startup/health verification to validate the test path. |

## 14. Full System Test & Bug Fixes (Ollama Path) — 2026-06-24
All three servers started (backend :8000, web :8080, admin :8001) and smoke-tested end-to-end with Ollama qwen2.5:1.5b. Three code bugs found and fixed during live testing. Final result: 24/24 tests pass.

**Bugs fixed:**

| # | File | Bug | Fix |
|---|---|---|---|
| 1 | `faia-web/web_server.py` | Starlette 1.3.x changed `TemplateResponse` signature — old call `(name, context_dict)` raises `TypeError: unhashable type: dict`. Every page load returns 500. | Updated to new signature: `TemplateResponse(request, name, context)` |
| 2 | `faia-web/web_server.py` | `_TIMEOUT = (3, 27)` — 27s read timeout cuts RAG queries mid-response (RAG prompt is much longer than plain chat). | Raised to `(3, 120)` |
| 3 | `backend/services/backend_service.py` | Chat endpoint checked `model_service.is_model_loaded()` before every response. With `MODEL_PROVIDER=ollama` the local model never loads, so this flag is always `False` → every chat request returned 503 "Qwen model not available". | Added provider check: block only if `MODEL_PROVIDER=local` and model not loaded. Ollama and OpenAI skip the check. |

**Environment fixes (not code):**

| # | What | Detail |
|---|---|---|
| 4 | `pip install transformers --upgrade` | `sentence-transformers 5.x` requires `huggingface-hub>=1.5` but `transformers 4.57` required `<1.0`. Upgraded `transformers` to 5.12.1 to resolve the conflict. |
| 5 | Jinja2 pinned to 3.1.4 | Jinja2 3.1.6 has a cache-key bug with newer Starlette. Pinned to 3.1.4. |
| 6 | `testprof` DB role fixed | User was created as `STUDENT` — fixed to `PROFESSOR` via direct SQL so materials upload endpoint accepts it. |

**Data changes:**

| # | File | Detail |
|---|---|---|
| 7 | `backend/services/uploads/sample_course_material.txt` | Created sample course doc (CS401 — Introduction to AI, 6 chapters, ~4KB) for RAG smoke testing. Uploaded and indexed via `/materials/upload` + `/materials/15/process`. 2 chunks indexed into ChromaDB. |
| 8 | `.env` | Added `ENABLE_RAG=true` |
| 9 | `test_system.py` | Updated credentials to real DB users (`kiro`, `testprof`, `akino`) and correct forgot-password email. |

**Test results:**

| Run | Score | Notes |
|---|---|---|
| Before fixes | 5/19 | All logins failed (wrong creds), web returned 500, chat returned 503 |
| After cred fix + web fix | 21/24 | Chat working, RAG timed out at 27s |
| After all fixes | **24/24** | All modules pass. AI response times: turn 1 = 11.3s, turn 2 = 7.3s, RAG = 15.4s |

| 81 | 2026-06-24 | 14:00 | FIX | faia-web/web_server.py | Starlette 1.3.x TemplateResponse signature fix (unhashable dict bug) |
| 82 | 2026-06-24 | 14:05 | FIX | faia-web/web_server.py | Raised read timeout from 27s to 120s for RAG compatibility |
| 83 | 2026-06-24 | 14:10 | FIX | backend/services/backend_service.py | Ollama provider guard on model_loaded check — Ollama/OpenAI no longer blocked by local model state |
| 84 | 2026-06-24 | 14:15 | ADD | backend/services/uploads/sample_course_material.txt | Sample CS401 course material for RAG smoke testing |
| 85 | 2026-06-24 | 14:20 | EDIT | .env | ENABLE_RAG=true |
| 86 | 2026-06-24 | 14:20 | EDIT | test_system.py | Real DB credentials + correct email for forgot-password test |
| 87 | 2026-06-24 | 14:45 | TEST | Full system test | 24/24 passed — backend, web, admin, auth, chat (Ollama), RAG, context, file upload, admin endpoints, token tracking |

## 15. UI/UX Notes (Backlog) — 2026-06-24

| # | Area | Issue | Priority |
|---|---|---|---|
| UI-01 | File upload indicator | 📎 emoji shown alongside message text when a file is attached is not ideal — needs a proper file card/badge UI component instead | Later |
| UI-02 | Model awareness of uploaded file | After file upload, model responds "please upload a document" because the system prompt doesn't tell it a file is already attached until the user sends a message — model should be primed with file context immediately on upload | Later |

## 16. Manual Testing Session — 2026-06-24

**Web UI (localhost:8080) — all pass:**
- Login / logout ✅
- Guest mode ✅
- Chat (no RAG) ✅
- Chat (RAG) ✅ — source citation shows "sample_course_material, Page 1"
- File upload ✅ — file attaches and is sent as context with message
- Chat history / context memory ✅
- Hamburger menu (logout, change password, history) ✅

**Admin Panel (localhost:8090 → API :8001):**
- Login ✅
- Dashboard ✅
- Users list ✅
- Sessions ✅
- Audit log ✅ — was empty due to missing `details` column in live DB, fixed with ALTER TABLE
- Materials ✅ — shows all indexed docs with chunk count and READY status
- System ✅

**Bugs found and fixed during manual testing:**

| # | Issue | Fix |
|---|---|---|
| 1 | Admin frontend port 5500 blocked by Windows reserved port range (5344–5943 excluded by Hyper-V) | Served admin frontend on port 8090 instead |
| 2 | Audit log empty + add user returns 500 | `audit_logs` table in live DB was missing `details TEXT` column (schema had it, live DB predated it). Fixed: `ALTER TABLE audit_logs ADD COLUMN details TEXT NULL` |

**Known issues / backlog:**

| # | Area | Issue |
|---|---|---|
| B-01 | Admin: add user | Returns 500 instead of 400 when username/email already exists — admin `main.py` catches the duplicate error but re-raises as 500 instead of passing the 400 through |
| B-02 | Admin frontend port | 5500 hardcoded in `start_all.bat` but blocked on this machine by Windows — needs note in README for Windows users |

| 88 | 2026-06-24 | 15:20 | FIX | live DB | ALTER TABLE audit_logs ADD COLUMN details TEXT — schema already correct, live DB was behind |
| 89 | 2026-06-24 | 15:25 | NOTE | admin/frontend | Port 5500 blocked by Windows Hyper-V reserved range, used 8090 for this session |

## 17. System Page Fixes — 2026-06-24

| # | Fix | Detail |
|---|---|---|
| 1 | Tokenization tab badge | Changed from `status-gray / Not Implemented` to `status-green / Active` — tab is fully functional |
| 2 | Active sessions count | Was counting ALL sessions ever created (279). Fixed to filter `logout_time == NULL` → now shows real active sessions (10) |
| 3 | Total files count | Was hardcoded 0 ("feature disabled"). Fixed to query `course_materials WHERE status='ready'` → now shows 6 |
| 4 | API Response 0ms card | Replaced with Disk Usage card (real data from psutil: 92% used, 11.5 GB free) — 0ms was a placeholder with no tracking |
| 5 | Dead JS references | `requests-per-min`, `avg-response-time`, `error-rate`, `db-connections`, `cpu-circle`, `memory-circle` referenced in JS but not in HTML — fail silently. Noted as low-priority backlog (null-safe, no crash) |

| 90 | 2026-06-24 | 15:50 | FIX | admin/backend/main.py | system/health: active sessions now filters logout_time=NULL, total_files queries course_materials, disk_usage/disk_free added from psutil |
| 91 | 2026-06-24 | 15:50 | FIX | admin/frontend/pages/system.html | Tokenization tab badge: gray/Not Implemented → green/Active |
| 92 | 2026-06-24 | 15:50 | FIX | admin/frontend/js/system.js | Replaced 0ms API Response card with real Disk Usage card |
