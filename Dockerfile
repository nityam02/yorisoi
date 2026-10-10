# One Cloud Run service: FastAPI serves the API at /api and the built React app at /.

FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
WORKDIR /srv/api
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/api/ ./
COPY --from=web /web/dist /srv/web
ENV YORISOI_WEB_DIST=/srv/web YORISOI_CACHE_DIR=/tmp/yorisoi-cache YORISOI_STORE_DIR=/tmp/yorisoi-store PORT=8080
CMD ["sh", "-c", "exec /srv/api/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
