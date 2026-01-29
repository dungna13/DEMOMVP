# Auto-Bot Project

This project implements a 24/7 autonomous agent architecture designed for multitasking and Telegram integration.

## Project Structure

```text
auto-bot/
├── config/
│   ├── settings.yaml       # Global configuration
│   └── secrets.env         # Environment variables (Do not commit)
├── core/
│   ├── engine.py           # Main event loop
│   ├── task_queue.py       # Priority queue
│   ├── scheduler.py        # Job scheduler
│   └── memory.py           # Context management
├── interfaces/
│   └── telegram_bot.py     # Telegram interface
├── skills/
│   ├── network_scanner.py
│   ├── file_manager.py
│   └── web_search.py
├── database/
│   ├── models.py           # Data models
│   └── storage.py          # Database connection
├── logs/
├── main.py                 # Entry point
├── requirements.txt
└── Dockerfile
```

## Development Workflow

We follow a strict `dev` -> `feature` branching model to ensure stability.

### 1. Standard Workflow
Every change must be made on a new branch created from `dev`.

```bash
# 1. Switch to dev and update
git checkout dev
git pull origin dev

# 2. Create a new feature branch
git checkout -b feature/login

# ... (Write code, test) ...

# 3. Commit changes
git add .
git commit -m "Add login feature"

# 4. Push to GitHub
git push origin feature/login
```

### 2. Best Practices

| Category | Guideline |
| :--- | :--- |
| **Commit Authorship** | Ensure correct attribution. If pairing, use `Co-authored-by` in commit messages. |
| **Safety** | Always branch off `dev`. Never push directly to `main` or `dev` (configure Branch Protection). |
| **Staging** | Create a Pull Request (PR) from `feature/...` to `dev` for review before merging. |

### 3. Branch Protection Setup
To prevent errors, Repository Admins should enable **Branch Protection** rules for `main` and `dev`:
- Require Pull Request reviews before merging.
- Require status checks to pass.
- Do not allow direct pushes.
