# syntax=docker/dockerfile:1.7
# ── Stage 1: Builder ──────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# 先复制 requirements 以利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

# 安全：非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# 复制依赖
COPY --from=builder /install /usr/local

# 复制应用代码（migrations/ 用于启动时 DDL 演进，data/ 用于 SEED_ON_STARTUP 种子数据）
COPY src/        ./src/
COPY migrations/ ./migrations/
COPY data/       ./data/

# 创建上传目录
RUN mkdir -p uploads && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# 健康检查：依赖 httpx（已在 requirements.txt 中）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/api/v1/health'); assert r.status_code == 200"

# 注意：使用单 worker，避免多进程 fork 导致 asyncio.create_task
# 的后台审查任务（进度推送）在请求结束后丢失。
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
