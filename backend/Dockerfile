# ── 构建阶段：安装依赖（利用 Docker 层缓存，代码变更不重装依赖）──
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-editable

# ── 运行阶段：只带虚拟环境和源码，镜像最小化 ──
FROM python:3.14-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY app ./app

EXPOSE 8000
# 生产多 worker；SSE 长连接场景 worker 数不宜过大
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
