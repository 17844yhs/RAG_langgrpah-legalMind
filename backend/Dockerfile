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
# 单进程是设计契约，不是省事：信号量/令牌桶/熔断器均为进程级单例，
# 多 worker 会把所有限额静默翻倍（16→32、300RPM→600RPM）并复制模型内存。
# 本应用瓶颈在 LLM 上游（p90 13.8s），单进程远未饱和（基础设施层实测 458 QPS）；
# 扩容走容器副本数（checkpoint 在 PG、共享缓存在 Redis，无进程间共享内存，天然可横向扩展）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
