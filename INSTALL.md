# Golf Game Installation Guide

Complete guide for installing and running the Golf card game server.

## Table of Contents

- [Quick Start](#quick-start)
- [Requirements](#requirements)
- [Development Setup](#development-setup)
- [Production Installation](#production-installation)
- [Docker Deployment](#docker-deployment)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

The fastest way to get started is using the interactive installer:

```bash
./scripts/install.sh
```

This provides a menu with options for:
- Development setup (Docker services + virtualenv + dependencies)
- Production installation to /opt/golfgame
- Systemd service configuration
- Status checks

---

## Requirements

### For Development

- **Python 3.11+** (3.12, 3.13, 3.14 also work)
- **Docker** and **Docker Compose** (for PostgreSQL and Redis)
- **Git**

### For Production

- **Python 3.11+**
- **PostgreSQL 16+**
- **Redis 7+**
- **systemd** (for service management)
- **nginx** (recommended, for reverse proxy)

---

## Development Setup

### Option A: Using the Installer (Recommended)

```bash
./scripts/install.sh
# Select option 1: Development Setup
```

This will:
1. Start PostgreSQL and Redis in Docker containers
2. Create a Python virtual environment
3. Install all dependencies
4. Generate a `.env` file configured for local development

### Option B: Manual Setup

#### 1. Start Docker Services

```bash
docker-compose -f docker-compose.dev.yml up -d
```

This starts:
- **PostgreSQL** on `localhost:5432` (user: `golf`, password: `devpassword`, database: `golf`)
- **Redis** on `localhost:6379`

Verify services are running:
```bash
docker-compose -f docker-compose.dev.yml ps
```

#### 2. Create Python Virtual Environment

```bash
# Create venv in project root
python3 -m venv .

# Activate it
source bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies (including dev tools)
pip install -e ".[dev]"
```

#### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` for development:

```bash
HOST=0.0.0.0
PORT=8000
DEBUG=true
LOG_LEVEL=DEBUG
ENVIRONMENT=development

DATABASE_URL=postgresql://golf:devpassword@localhost:5432/golf
POSTGRES_URL=postgresql://golf:devpassword@localhost:5432/golf
```

#### 4. Run the Development Server

```bash
cd server
../bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Or use the helper script:

```bash
./scripts/dev-server.sh
```

The server will be available at http://localhost:8000

#### 5. Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Should return: {"status":"ok","timestamp":"..."}
```

### Stopping Development Services

```bash
# Stop the server: Ctrl+C

# Stop Docker containers
docker-compose -f docker-compose.dev.yml down

# Stop and remove volumes (clean slate)
docker-compose -f docker-compose.dev.yml down -v
```

---

## Production Installation

### Option A: Using the Installer (Recommended)

```bash
sudo ./scripts/install.sh
# Select option 2: Production Install to /opt/golfgame
```

### Option B: Manual Installation

#### 1. Install System Dependencies

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql redis-server nginx

# Start and enable services
sudo systemctl enable --now postgresql redis-server nginx
```

#### 2. Create PostgreSQL Database

```bash
sudo -u postgres psql << EOF
CREATE USER golf WITH PASSWORD 'your_secure_password';
CREATE DATABASE golf OWNER golf;
GRANT ALL PRIVILEGES ON DATABASE golf TO golf;
EOF
```

#### 3. Create Installation Directory

```bash
sudo mkdir -p /opt/golfgame
sudo chown $USER:$USER /opt/golfgame
```

#### 4. Clone and Install Application

```bash
cd /opt/golfgame
git clone https://github.com/alee/golfgame.git .

# Create virtual environment
python3 -m venv .
source bin/activate

# Install application
pip install --upgrade pip
pip install .
```

#### 5. Configure Production Environment

Create `/opt/golfgame/.env`:

```bash
# Generate a secret key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > /opt/golfgame/.env << EOF
HOST=0.0.0.0
PORT=8000
DEBUG=false
LOG_LEVEL=INFO
ENVIRONMENT=production

DATABASE_URL=postgresql://golf:your_secure_password@localhost:5432/golf
POSTGRES_URL=postgresql://golf:your_secure_password@localhost:5432/golf

SECRET_KEY=$SECRET_KEY

MAX_PLAYERS_PER_ROOM=6
ROOM_TIMEOUT_MINUTES=60

# Optional: Error tracking with Sentry
# SENTRY_DSN=https://your-sentry-dsn

# Optional: Email via Resend
# RESEND_API_KEY=your-api-key
EOF

# Secure the file
chmod 600 /opt/golfgame/.env
```

#### 6. Set Ownership

```bash
sudo chown -R www-data:www-data /opt/golfgame
```

#### 7. Create Systemd Service

Create `/etc/systemd/system/golfgame.service`:

```ini
[Unit]
Description=Golf Card Game Server
Documentation=https://github.com/alee/golfgame
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/golfgame/server
Environment="PATH=/opt/golfgame/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/golfgame/.env
ExecStart=/opt/golfgame/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/golfgame

[Install]
WantedBy=multi-user.target
```

#### 8. Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable golfgame
sudo systemctl start golfgame

# Check status
sudo systemctl status golfgame

# View logs
journalctl -u golfgame -f
```

#### 9. Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/golfgame`:

```nginx
upstream golfgame {
    server 127.0.0.1:8000;
    keepalive 64;
}

server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL configuration (use certbot for Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://golfgame;
        proxy_http_version 1.1;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for WebSocket
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/golfgame /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 10. SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Docker Deployment

### Build the Docker Image

```bash
./scripts/docker-build.sh

# Or manually:
docker build -t golfgame:latest .
```

### Development with Docker

```bash
# Start dev services only (PostgreSQL + Redis)
docker-compose -f docker-compose.dev.yml up -d
```

### Production with Docker Compose

```bash
# Set required environment variables
export DB_PASSWORD="your-secure-database-password"
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export ACME_EMAIL="your-email@example.com"
export DOMAIN="your-domain.com"

# Optional
export RESEND_API_KEY="your-resend-key"
export SENTRY_DSN="your-sentry-dsn"

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f app

# Scale app instances
docker-compose -f docker-compose.prod.yml up -d --scale app=3
```

The production compose file includes:
- **app**: The Golf game server (scalable)
- **postgres**: PostgreSQL database
- **redis**: Redis for sessions
- **traefik**: Reverse proxy with automatic HTTPS

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ENVIRONMENT` | `production` | Environment name |
| `DATABASE_URL` | - | PostgreSQL URL (event sourcing, game logs, stats) |
| `POSTGRES_URL` | - | PostgreSQL URL for auth/stats (can be same as DATABASE_URL) |
| `SECRET_KEY` | - | Secret key for JWT tokens |
| `MAX_PLAYERS_PER_ROOM` | `6` | Maximum players per game room |
| `ROOM_TIMEOUT_MINUTES` | `60` | Inactive room cleanup timeout |
| `ROOM_CODE_LENGTH` | `4` | Length of room codes |
| `DEFAULT_ROUNDS` | `9` | Default holes per game |
| `SENTRY_DSN` | - | Sentry error tracking DSN |
| `RESEND_API_KEY` | - | Resend API key for emails |
| `RATE_LIMIT_ENABLED` | `false` | Enable rate limiting |

### File Locations

| Path | Description |
|------|-------------|
| `/opt/golfgame/` | Production installation root |
| `/opt/golfgame/.env` | Production environment config |
| `/opt/golfgame/server/` | Server application code |
| `/opt/golfgame/client/` | Static web client |
| `/opt/golfgame/bin/` | Python virtualenv binaries |
| `/etc/systemd/system/golfgame.service` | Systemd service file |
| `/etc/nginx/sites-available/golfgame` | Nginx site config |

---

## Troubleshooting

### Check Service Status

```bash
# Systemd service
sudo systemctl status golfgame
journalctl -u golfgame -n 100

# Docker containers
docker-compose -f docker-compose.dev.yml ps
docker-compose -f docker-compose.dev.yml logs

# Using the installer
./scripts/install.sh
# Select option 6: Show Status
```

### Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","timestamp":"..."}
```

### Common Issues

#### "No module named 'config'"

The server must be started from the `server/` directory:

```bash
cd /opt/golfgame/server
../bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

#### "Connection refused" on PostgreSQL

1. Check PostgreSQL is running:
   ```bash
   sudo systemctl status postgresql
   # Or for Docker:
   docker ps | grep postgres
   ```

2. Verify connection settings in `.env`

3. Test connection:
   ```bash
   psql -h localhost -U golf -d golf
   ```

#### "POSTGRES_URL not configured" warning

Add `POSTGRES_URL` to your `.env` file. This is required for authentication and stats features.

#### Broken virtualenv symlinks

If Python was upgraded, the virtualenv symlinks may break. Recreate it:

```bash
rm -rf bin lib lib64 pyvenv.cfg include share
python3 -m venv .
source bin/activate
pip install -e ".[dev]"  # or just: pip install .
```

#### Permission denied on /opt/golfgame

```bash
sudo chown -R www-data:www-data /opt/golfgame
sudo chmod 600 /opt/golfgame/.env
```

### Updating

#### Development

```bash
git pull
source bin/activate
pip install -e ".[dev]"
# Server auto-reloads with --reload flag
```

#### Production

```bash
cd /opt/golfgame
sudo systemctl stop golfgame
sudo -u www-data git pull
sudo -u www-data ./bin/pip install .
sudo systemctl start golfgame
```

#### Docker

```bash
docker-compose -f docker-compose.prod.yml down
git pull
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

---

## Scripts Reference

| Script | Description |
|--------|-------------|
| `scripts/install.sh` | Interactive installer menu |
| `scripts/dev-server.sh` | Start development server |
| `scripts/docker-build.sh` | Build production Docker image |

---

## Support

- GitHub Issues: https://github.com/alee/golfgame/issues
- Documentation: See `README.md` for game rules and API docs
