# Telegram File Storage Bot

A feature-rich Telegram bot for storing and managing files in a private channel with MongoDB backend.

## Features

- **Admin-only uploads** — Only designated admins can upload files
- **Download quota system** — Per-user daily bandwidth and download count limits (resets at midnight UTC)
- **Unlimited downloads for admins** — Admins bypass quota restrictions
- **Token verification for downloads** — Non-admins must verify a token before downloading (30-min session)
- **Duplicate detection** — Automatically detects if you've already uploaded a file
- **File organization** — Tags, rename, search by filename or tag
- **File sharing** — Generate share codes for others to claim files
- **Auto-expiry** — Set files to expire after 1, 7, or 30 days
- **Admin dashboard** — View stats, manage download quotas, delete any file

## Requirements

- Python 3.11+
- MongoDB 7.0+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- A private Telegram channel for file storage

## Setup

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/tg-bot-v2.git
cd tg-bot-v2
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Create Storage Channel

1. Create a private Telegram channel
2. Add your bot as an administrator with permission to post messages
3. Get the channel ID (should look like `-1001234567890`)

### 3. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Telegram
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
STORAGE_CHANNEL_ID=-1001234567890

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=tg_file_storage

# Security
ALLOWED_USER_IDS=           # Empty = open access for all users
ADMIN_USER_IDS=123456789    # Comma-separated admin user IDs

# Quota (Download quota - resets daily at midnight UTC)
DEFAULT_QUOTA_MB=500        # Legacy - kept for backward compatibility
DEFAULT_BANDWIDTH_LIMIT_MB=500  # Daily bandwidth limit per user in MB (0 = unlimited)
DEFAULT_DOWNLOAD_LIMIT=0    # Daily download count limit (0 = unlimited)

# Auto-Expiry
DEFAULT_EXPIRY_DAYS=0       # 0 = no auto-expiry
EXPIRY_CLEANUP_INTERVAL=3600

# App
LOG_LEVEL=INFO
MAX_FILE_SIZE_MB=50
```

### 4. Run

```bash
python run.py
```

## Docker Deployment

```bash
docker-compose up -d
```

This starts both the bot and MongoDB container.

## Usage

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message |
| `/help` | Show all commands |
| `/list` | Browse your files (paginated) |
| `/get <id>` | Retrieve a file by ID |
| `/search <query>` | Search files by filename |
| `/tag <tag>` | Find files by tag |
| `/rename <id>` | Rename a file |
| `/delete <id>` | Delete a file |
| `/share <id>` | Generate a share code |
| `/claim <code>` | Claim a shared file |
| `/mystats` | View your download quota usage |
| `/settoken` | Set your download verification token |
| `/verify` | Verify token to enable downloads (30-min session) |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/admin` | Open admin dashboard |
| `/setquota <user_id> <mb>` | Set user quota (0 = unlimited) |
| `/delfile <record_id>` | Force-delete any file |
| `/userinfo <user_id>` | View user stats |

### File Actions

After uploading, interactive buttons allow you to:
- **Tag** — Add tags for organization
- **Rename** — Change display name
- **Share** — Generate share code
- **Expiry** — Set auto-delete timer
- **Delete** — Remove file

## Architecture

```
bot/
├── main.py              # Entry point
├── config.py            # Settings (Pydantic)
├── database/
│   ├── connection.py    # MongoDB connection
│   └── repositories/
│       ├── file_repo.py # File CRUD operations
│       └── quota_repo.py # Quota tracking
├── handlers/
│   ├── upload.py        # File upload (admin-only)
│   ├── download.py      # File retrieval & management
│   ├── admin.py         # Admin panel
│   └── common.py        # /start, /help
├── middlewares/
│   └── auth.py          # Allowlist middleware
├── models/
│   └── file_record.py   # Data models
├── tasks/
│   └── expiry_task.py   # Background expiry cleanup
└── utils/
    ├── file_utils.py    # Helpers
    ├── keyboards.py     # Inline keyboards
    └── states.py        # FSM states
```

## Tech Stack

- **aiogram 3.7** — Telegram Bot framework
- **Motor** — Async MongoDB driver
- **Pydantic** — Settings & data validation
- **MongoDB 7.0** — Database

## License

MIT
