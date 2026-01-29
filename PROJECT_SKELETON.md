# Auto-Bot Project Skeleton (Telegram-based)

This skeleton outlines the architecture for a 24/7 autonomous agent similar to "Clawdbot", capable of multitasking and communicating via Telegram.

## 1. Project Structure

```text
auto-bot/
├── config/
│   ├── settings.yaml       # Global configuration (API keys, timeouts)
│   └── secrets.env         # Environment variables (Tokens - DO NOT COMMIT)
├── core/
│   ├── engine.py           # Main infinite loop (24/7 heartbeat)
│   ├── task_queue.py       # Priority queue for multi-tasking
│   ├── scheduler.py        # Cron-like job scheduler
│   └── memory.py           # Short-term (RAM) and Long-term (DB) memory context
├── interfaces/
│   └── telegram_bot.py     # Wrapper for python-telegram-bot (Async)
├── skills/                 # Pluggable skills (Multi-task capabilities)
│   ├── network_scanner.py
│   ├── file_manager.py
│   └── web_search.py
├── database/
│   ├── models.py           # SQL/ORM models
│   └── storage.py          # Database connection handler
├── logs/                   # Log files
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── Dockerfile              # For 24/7 deployment
└── README.md
```

## 2. Core Components

### `main.py`
Initializes the `Engine`, connects to `Database`, starts the `TelegramBot` interface, and enters the main event loop.

### `core/engine.py`
The "Brain". It checks the `TaskQueue`, processes scheduled jobs, and routes messages from Telegram to the appropriate `Skill`.

### `interfaces/telegram_bot.py`
Handles user interaction.
- **Commands**: `/start`, `/status`, `/add_task`
- **Notifications**: Sends alerts when tasks complete or errors occur.

### `core/task_queue.py`
Allows the bot to handle multiple things at once (concurrency). Uses `asyncio` to run long-running tasks (like scanning or downloading) without freezing the bot.

## 3. Technology Stack
- **Language**: Python 3.11+
- **Framework**: `python-telegram-bot` (JobQueue & Async support)
- **Database**: SQLite (local) or PostgreSQL (scalable)
- **Deployment**: Docker (ensures it runs 24/7 on any server/PC)

---

## 4. Git Collaboration Guide (Multi-Author)

Since your team has 3 members, you can verify contributions using the `Co-authored-by` footer in git commits. This allows GitHub to show multiple avatars on a single commit.

### How to commit with multiple authors
When making a commit via command line, add two empty lines after your message, then list co-authors:

```bash
git commit -m "Refactor the task manager core

Co-authored-by: Name1 <email1@example.com>
Co-authored-by: Name2 <email2@example.com>"
```

### Allowing others to push to GitHub
1. **Create a Repository** on GitHub.
2. **Invite Collaborators**:
   - Go to `Settings` -> `Collaborators` -> `Add people`.
   - Enter the usernames/emails of your 2 teammates.
   - They must accept the invite email.
3. **Workflow**:
   - Everyone clones the repo: `git clone <url>`
   - Before working: `git pull`
   - Make changes -> `git add .` -> `git commit` (use the template above if pair-programming)
   - Push changes: `git push origin main`
