# FAIA — Future Artificial Intelligence Assistant

An AI-powered educational chatbot built for university students. Professors upload course materials, students query them through a chat interface powered by RAG (Retrieval-Augmented Generation) and a local LLM — no cloud API required.

Built as a graduation project at Future University of Sudan by Ahmed Mahmoud Hamza.

---

## Features

- **AI Chat** — conversational interface powered by a local Qwen model via Ollama/HuggingFace
- **RAG** — professors upload PDF/DOCX/TXT course materials, students get answers grounded in actual course content
- **Role-based access** — Student, Professor, Admin, and Guest roles with JWT authentication
- **Conversation history** — full per-user chat history stored in MySQL
- **Admin panel** — user management, session monitoring, token limits, audit logs, database backups
- **Android app** — Kotlin WebView wrapper, configurable server IP, tested on real device
- **24/24 automated tests passing** — full system test suite included

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI / RAG | Qwen (local via Ollama or HuggingFace), sentence-transformers, ChromaDB |
| Database | MySQL / MariaDB, SQLAlchemy |
| Frontend | HTML, CSS, JavaScript (vanilla), Jinja2 |
| Admin Panel | FastAPI backend + plain HTML/JS frontend |
| Mobile | Android (Kotlin, WebView) |
| Auth | JWT (PyJWT), bcrypt |

---

## Project Structure

```
FAIA/
├── backend/                  # Main AI backend
│   ├── services/             # AI service, RAG, cache, health check
│   │   ├── backend_service.py            # Main FastAPI app (port 8000)
│   │   ├── rag_service.py            # ChromaDB RAG pipeline
│   │   ├── model_service.py          # Qwen model loading and inference
│   │   └── requirements.txt
│   ├── configuration/        # Config manager + faia_config.json
│   └── database/             # SQLAlchemy database integration
│
├── admin/                    # Admin panel
│   ├── backend/              # FastAPI admin API (port 8001)
│   └── frontend/             # HTML/JS admin dashboard (port 5500)
│
├── faia-web/                 # Web chat interface (port 8080)
│   ├── templates/            # Jinja2 HTML templates
│   └── static/               # CSS, JS, images
│
├── faia-android/             # Android app (Kotlin)
│   └── app/src/main/         # MainActivity + SettingsActivity
│
├── .env.example              # Environment variable template
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- MySQL or MariaDB running locally
- A local Qwen model downloaded (see model setup below)
- Java 17+ (for Android build, optional)

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/FAIA.git
cd FAIA
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:
- `JWT_SECRET_KEY` — generate a random secret
- `DB_PASSWORD` — your MySQL password
- `QWEN_MODEL_PATH` — path to your local Qwen model directory

### 3. Set up the database

Import the schema into MySQL:

```bash
mysql -u root -p < backend/database/faia_chat_system.sql
```

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Set up the AI model

FAIA supports three model providers. Set `MODEL_PROVIDER` in your `.env`:

**Option A — Ollama (easiest, recommended for quick start):**
```bash
# Install Ollama: https://ollama.com
ollama pull qwen2.5:1.5b    # fast, good for testing
ollama pull qwen2.5:7b      # better quality
```
Then set in `.env`:
```
MODEL_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:1.5b
```

**Option B — Local HuggingFace (original, best quality control):**
```bash
pip install huggingface-cli
huggingface-cli download Qwen/Qwen2.5-0.5B-Instruct --local-dir ./models/qwen-0.5b
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct --local-dir ./models/qwen-1.5b
```
Then set in `.env`:
```
MODEL_PROVIDER=local
QWEN_MODEL_PATH=./models/qwen-0.5b
```

**Option C — OpenAI (cloud, no local hardware needed):**
```
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o-mini
```
Note: requires `pip install openai`

### 6. Start the system

Start each service in a separate terminal:

```bash
# Terminal 1 — Main backend (port 8000)
cd backend/services
python backend_service.py

# Terminal 2 — Web chat interface (port 8080)
cd faia-web
python web_server.py

# Terminal 3 — Admin API (port 8001)
cd admin/backend
python main.py

# Terminal 4 — Admin frontend (use any free port, 5500 is blocked on Windows by Hyper-V)
cd admin/frontend
python -m http.server 8090
```

| Service | URL |
|---|---|
| Chat Interface | http://localhost:8080 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Admin Panel | http://localhost:8090 (or any free port — see note below) |
| Admin API | http://localhost:8001 |

> **Note on Admin Panel port:** The admin frontend is served by Python's built-in HTTP server. Port 5500 is blocked on Windows by Hyper-V's reserved port range (typically 5344–5943). Use any available port above 8000, e.g. `python -m http.server 8090` from the `admin/frontend/` directory.

### Default admin credentials

Create your admin user by registering through the API or directly in MySQL. The system uses SHA256 with random salts for password hashing.

---

## Running Tests

With all services running:

```bash
python test_system.py
```

The test script reads credentials from environment variables. Set them before running:

```bash
set TEST_STUDENT_USER=yourstudent
set TEST_STUDENT_PASS=yourpass
set TEST_PROF_USER=yourprofessor
set TEST_PROF_PASS=yourpass
set TEST_ADMIN_USER=youradmin
set TEST_ADMIN_PASS=yourpass
```

Expected output: **24/24 tests passing** across 8 test categories (health, auth, chat, context retention, file upload, admin, password reset, token tracking).

---

## Android App

The Android app is a Kotlin WebView that connects to the FAIA web interface over your local network.

1. Open `faia-android/` in Android Studio
2. Build the project (requires Java 17+)
3. On first launch, tap the settings icon and enter your server IP
4. Default port: `8080`

A pre-built APK is not included — build from source.

---

## Modules

| Module | Description |
|---|---|
| Authentication | JWT-based login/register, role management, password reset |
| Academic Assistance | AI chat with RAG, context retention across messages |
| Professor Support | Material upload (PDF/DOCX/TXT), ChromaDB indexing |
| Context Retention | Per-session conversation memory injected into prompts |
| Mobile Access | Android WebView wrapper with configurable server IP |
| Admin Management | User CRUD, session control, token limits, audit logs, backups |

---

## Configuration

All AI behavior, RAG settings, prompts, and moderation rules are in `backend/configuration/faia_config.json`. Key settings:

- `models.qwen.path` — model directory path
- `rag.retrieval.top_k` — how many chunks to retrieve per query
- `rag.retrieval.min_similarity` — minimum cosine similarity threshold
- `moderation.risk_levels` — keyword-based content moderation rules

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Author

Ahmed Mahmoud Hamza
IT Graduate, Future University of Sudan
