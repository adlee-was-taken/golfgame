# V2_07: Production Deployment & Operations

> **Scope**: Docker, deployment, health checks, monitoring, security, rate limiting
> **Dependencies**: All other V2 documents
> **Complexity**: High (DevOps/Infrastructure)

---

## Overview

Production readiness requires:
- **Containerization**: Docker images for consistent deployment
- **Health Checks**: Liveness and readiness probes
- **Monitoring**: Metrics, logging, error tracking
- **Security**: HTTPS, headers, secrets management
- **Rate Limiting**: API protection from abuse (Phase 1 priority)
- **Graceful Operations**: Zero-downtime deploys, proper shutdown

---

## 1. Docker Configuration

### Application Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim as base

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/ ./server/
COPY client/ ./client/

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql://golf:${DB_PASSWORD}@postgres:5432/golfgame
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - RESEND_API_KEY=${RESEND_API_KEY}
      - SENTRY_DSN=${SENTRY_DSN}
      - ENVIRONMENT=production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure
        max_attempts: 3
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
    networks:
      - internal
      - web
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.golf.rule=Host(`golf.example.com`)"
      - "traefik.http.routers.golf.tls=true"
      - "traefik.http.routers.golf.tls.certresolver=letsencrypt"

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: python -m arq server.worker.WorkerSettings
    environment:
      - DATABASE_URL=postgresql://golf:${DB_PASSWORD}@postgres:5432/golfgame
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    deploy:
      replicas: 1
      resources:
        limits:
          memory: 256M

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: golfgame
      POSTGRES_USER: golf
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U golf -d golfgame"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - internal

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - internal

  traefik:
    image: traefik:v2.10
    command:
      - "--api.dashboard=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL}"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt
    networks:
      - web

volumes:
  postgres_data:
  redis_data:
  letsencrypt:

networks:
  internal:
  web:
    external: true
```

---

## 2. Health Checks & Readiness

### Health Endpoint Implementation

```python
# server/health.py
from fastapi import APIRouter, Response
from datetime import datetime
import asyncpg
import redis.asyncio as redis

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    """Basic liveness check - is the app running?"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@router.get("/ready")
async def readiness_check(
    db: asyncpg.Pool = Depends(get_db_pool),
    redis_client: redis.Redis = Depends(get_redis)
):
    """Readiness check - can the app handle requests?"""
    checks = {}
    overall_healthy = True

    # Check database
    try:
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        overall_healthy = False

    # Check Redis
    try:
        await redis_client.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as e:
        checks["redis"] = {"status": "error", "message": str(e)}
        overall_healthy = False

    status_code = 200 if overall_healthy else 503
    return Response(
        content=json.dumps({
            "status": "ok" if overall_healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat()
        }),
        status_code=status_code,
        media_type="application/json"
    )

@router.get("/metrics")
async def metrics(
    db: asyncpg.Pool = Depends(get_db_pool),
    redis_client: redis.Redis = Depends(get_redis)
):
    """Expose application metrics for monitoring."""
    async with db.acquire() as conn:
        active_games = await conn.fetchval(
            "SELECT COUNT(*) FROM games WHERE completed_at IS NULL"
        )
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        games_today = await conn.fetchval(
            "SELECT COUNT(*) FROM games WHERE created_at > NOW() - INTERVAL '1 day'"
        )

    connected_players = await redis_client.scard("connected_players")

    return {
        "active_games": active_games,
        "total_users": total_users,
        "games_today": games_today,
        "connected_players": connected_players,
        "timestamp": datetime.utcnow().isoformat()
    }
```

---

## 3. Rate Limiting (Phase 1 Priority)

Rate limiting is a Phase 1 priority for security. Implement early to prevent abuse.

### Rate Limiter Implementation

```python
# server/ratelimit.py
from fastapi import Request, HTTPException
from typing import Optional
import redis.asyncio as redis
import time
import hashlib

class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> tuple[bool, dict]:
        """Check if request is allowed under rate limit.

        Returns (allowed, info) where info contains:
        - remaining: requests remaining in window
        - reset: seconds until window resets
        - limit: the limit that was applied
        """
        now = int(time.time())
        window_key = f"ratelimit:{key}:{now // window_seconds}"

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(window_key)
            pipe.expire(window_key, window_seconds)
            results = await pipe.execute()

        current_count = results[0]
        remaining = max(0, limit - current_count)
        reset = window_seconds - (now % window_seconds)

        info = {
            "remaining": remaining,
            "reset": reset,
            "limit": limit
        }

        return current_count <= limit, info

    def get_client_key(self, request: Request, user_id: Optional[str] = None) -> str:
        """Generate rate limit key for client."""
        if user_id:
            return f"user:{user_id}"

        # For anonymous users, use IP hash
        client_ip = request.client.host
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        # Hash IP for privacy
        return f"ip:{hashlib.sha256(client_ip.encode()).hexdigest()[:16]}"


# Rate limit configurations per endpoint type
RATE_LIMITS = {
    "api_general": (100, 60),      # 100 requests per minute
    "api_auth": (10, 60),          # 10 auth attempts per minute
    "api_create_room": (5, 60),    # 5 room creations per minute
    "websocket_connect": (10, 60), # 10 WS connections per minute
    "email_send": (3, 300),        # 3 emails per 5 minutes
}
```

### Rate Limit Middleware

```python
# server/middleware.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limiter: RateLimiter):
        super().__init__(app)
        self.limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        # Determine rate limit tier based on path
        path = request.url.path

        if path.startswith("/api/auth"):
            limit, window = RATE_LIMITS["api_auth"]
        elif path == "/api/rooms":
            limit, window = RATE_LIMITS["api_create_room"]
        elif path.startswith("/api"):
            limit, window = RATE_LIMITS["api_general"]
        else:
            # No rate limiting for static files
            return await call_next(request)

        # Get user ID if authenticated
        user_id = getattr(request.state, "user_id", None)
        client_key = self.limiter.get_client_key(request, user_id)

        allowed, info = await self.limiter.is_allowed(
            f"{path}:{client_key}", limit, window
        )

        # Add rate limit headers to response
        response = await call_next(request) if allowed else JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": info["reset"]
            }
        )

        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        if not allowed:
            response.headers["Retry-After"] = str(info["reset"])

        return response
```

### WebSocket Rate Limiting

```python
# In server/main.py
async def websocket_endpoint(websocket: WebSocket):
    client_key = rate_limiter.get_client_key(websocket)

    allowed, info = await rate_limiter.is_allowed(
        f"ws_connect:{client_key}",
        *RATE_LIMITS["websocket_connect"]
    )

    if not allowed:
        await websocket.close(code=1008, reason="Rate limit exceeded")
        return

    # Also rate limit messages within the connection
    message_limiter = ConnectionMessageLimiter(
        max_messages=30,
        window_seconds=10
    )

    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()

            if not message_limiter.check():
                await websocket.send_json({
                    "type": "error",
                    "message": "Slow down! Too many messages."
                })
                continue

            await handle_message(websocket, data)
    except WebSocketDisconnect:
        pass
```

---

## 4. Security Headers & HTTPS

### Security Middleware

```python
# server/security.py
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Content Security Policy
        csp = "; ".join([
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",  # For inline styles
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self' wss://*.example.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ])
        response.headers["Content-Security-Policy"] = csp

        # HSTS (only in production)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        return response
```

### CORS Configuration

```python
# server/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://golf.example.com",
        "https://www.golf.example.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

---

## 5. Error Tracking with Sentry

### Sentry Integration

```python
# server/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.asyncpg import AsyncPGIntegration

if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        environment=os.getenv("ENVIRONMENT", "development"),
        traces_sample_rate=0.1,  # 10% of transactions for performance
        profiles_sample_rate=0.1,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            RedisIntegration(),
            AsyncPGIntegration(),
        ],
        # Filter out sensitive data
        before_send=filter_sensitive_data,
    )

def filter_sensitive_data(event, hint):
    """Remove sensitive data before sending to Sentry."""
    if "request" in event:
        headers = event["request"].get("headers", {})
        # Remove auth headers
        headers.pop("authorization", None)
        headers.pop("cookie", None)

    return event
```

### Custom Error Handler

```python
# server/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse
import sentry_sdk
import traceback

async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""

    # Log to Sentry
    sentry_sdk.capture_exception(exc)

    # Log locally
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Return generic error to client
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": request.state.request_id
        }
    )

# Register handler
app.add_exception_handler(Exception, global_exception_handler)
```

---

## 6. Structured Logging

### Logging Configuration

```python
# server/logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Format logs as JSON for aggregation."""

    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "game_id"):
            log_data["game_id"] = record.game_id

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)

def setup_logging():
    """Configure application logging."""
    handler = logging.StreamHandler()

    if os.getenv("ENVIRONMENT") == "production":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))

    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)

    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
```

### Request ID Middleware

```python
# server/middleware.py
import uuid

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response
```

---

## 7. Graceful Shutdown

### Shutdown Handler

```python
# server/main.py
import signal
import asyncio

shutdown_event = asyncio.Event()

@app.on_event("startup")
async def startup():
    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutdown initiated...")

    # Stop accepting new connections
    shutdown_event.set()

    # Save all active games to Redis
    await save_all_active_games()

    # Close WebSocket connections gracefully
    for ws in list(active_connections):
        try:
            await ws.close(code=1001, reason="Server shutting down")
        except:
            pass

    # Wait for in-flight requests (max 30 seconds)
    await asyncio.sleep(5)

    # Close database pool
    await db_pool.close()

    # Close Redis connections
    await redis_client.close()

    logger.info("Shutdown complete")

async def save_all_active_games():
    """Persist all active games before shutdown."""
    for game_id, game in active_games.items():
        try:
            await state_cache.save_game(game)
            logger.info(f"Saved game {game_id}")
        except Exception as e:
            logger.error(f"Failed to save game {game_id}: {e}")
```

---

## 8. Secrets Management

### Environment Configuration

```python
# server/config.py
from pydantic import BaseSettings, PostgresDsn, RedisDsn

class Settings(BaseSettings):
    # Database
    database_url: PostgresDsn

    # Redis
    redis_url: RedisDsn

    # Security
    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # Email
    resend_api_key: str
    email_from: str = "Golf Game <noreply@golf.example.com>"

    # Monitoring
    sentry_dsn: str = ""
    environment: str = "development"

    # Rate limiting
    rate_limit_enabled: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

### Production Secrets (Example for Docker Swarm)

```yaml
# docker-compose.prod.yml
secrets:
  db_password:
    external: true
  secret_key:
    external: true
  resend_api_key:
    external: true

services:
  app:
    secrets:
      - db_password
      - secret_key
      - resend_api_key
    environment:
      - DATABASE_URL=postgresql://golf@postgres:5432/golfgame?password_file=/run/secrets/db_password
```

---

## 9. Database Migrations

### Alembic Configuration

```ini
# alembic.ini
[alembic]
script_location = migrations
sqlalchemy.url = env://DATABASE_URL

[logging]
level = INFO
```

### Migration Script Template

```python
# migrations/versions/001_initial.py
"""Initial schema

Revision ID: 001
Create Date: 2024-01-01
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None

def upgrade():
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('is_admin', sa.Boolean(), default=False),
    )

    # Games table
    op.create_table(
        'games',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('room_code', sa.String(10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )

    # Events table
    op.create_table(
        'events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('game_id', sa.UUID(), sa.ForeignKey('games.id'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes
    op.create_index('idx_events_game_id', 'events', ['game_id'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_username', 'users', ['username'])

def downgrade():
    op.drop_table('events')
    op.drop_table('games')
    op.drop_table('users')
```

### Migration Commands

```bash
# Create new migration
alembic revision --autogenerate -m "Add user sessions"

# Run migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1

# Show current version
alembic current
```

---

## 10. Deployment Checklist

### Pre-deployment

- [ ] All environment variables set
- [ ] Database migrations applied
- [ ] Secrets configured in secret manager
- [ ] SSL certificates provisioned
- [ ] Rate limiting configured and tested
- [ ] Error tracking (Sentry) configured
- [ ] Logging aggregation set up
- [ ] Health check endpoints verified
- [ ] Backup strategy implemented

### Deployment

- [ ] Run database migrations
- [ ] Deploy new containers with rolling update
- [ ] Verify health checks pass
- [ ] Monitor error rates in Sentry
- [ ] Check application logs
- [ ] Verify WebSocket connections work
- [ ] Test critical user flows

### Post-deployment

- [ ] Monitor performance metrics
- [ ] Check database connection pool usage
- [ ] Verify Redis memory usage
- [ ] Review error logs
- [ ] Test graceful shutdown/restart

---

## 11. Monitoring Dashboard (Grafana)

### Key Metrics to Track

```yaml
# Example Prometheus metrics
metrics:
  # Application
  - http_requests_total
  - http_request_duration_seconds
  - websocket_connections_active
  - games_active
  - games_completed_total

  # Infrastructure
  - container_cpu_usage_seconds_total
  - container_memory_usage_bytes
  - pg_stat_activity_count
  - redis_connected_clients
  - redis_used_memory_bytes

  # Business
  - users_registered_total
  - games_played_today
  - average_game_duration_seconds
```

### Alert Rules

```yaml
# alertmanager rules
groups:
  - name: golf-alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"

      - alert: DatabaseConnectionExhausted
        expr: pg_stat_activity_count > 90
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Database connections near limit"

      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Container memory usage above 90%"
```

---

## 12. Backup Strategy

### Database Backups

```bash
#!/bin/bash
# backup.sh - Daily database backup

BACKUP_DIR=/backups
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/golfgame_${DATE}.sql.gz"

# Backup with pg_dump
pg_dump -h postgres -U golf golfgame | gzip > "$BACKUP_FILE"

# Upload to S3/B2/etc
aws s3 cp "$BACKUP_FILE" s3://golf-backups/

# Cleanup old local backups (keep 7 days)
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

# Cleanup old S3 backups (keep 30 days) via lifecycle policy
```

### Redis Persistence

```conf
# redis.conf
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

---

## Summary

This document covers all production deployment concerns:

1. **Docker**: Multi-stage builds, health checks, resource limits
2. **Rate Limiting**: Token bucket algorithm, per-endpoint limits (Phase 1 priority)
3. **Security**: Headers, CORS, CSP, HSTS
4. **Monitoring**: Sentry, structured logging, Prometheus metrics
5. **Operations**: Graceful shutdown, migrations, backups
6. **Deployment**: Checklist, rolling updates, health verification

Rate limiting is implemented in Phase 1 as a security priority to protect against abuse before public launch.
