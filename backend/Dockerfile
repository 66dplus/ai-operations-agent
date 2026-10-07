FROM node:24.14.1-bookworm-slim AS cli
WORKDIR /cli
COPY runtime-template/node/package*.json ./
RUN npm ci --omit=dev
FROM python:3.12.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/app/.venv PATH=/app/.venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.10.10
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --from=cli /usr/local/bin/node /usr/local/bin/node
COPY --from=cli /cli/node_modules ./runtime-template/node/node_modules
ENV APP_ROOT=/app OPENCODE_BIN=/app/runtime-template/node/node_modules/.bin/opencode
RUN useradd --uid 10001 --create-home operations && mkdir -p /app/runtime && chown operations:operations /app/runtime
COPY backend/operations ./operations
COPY backend/migrations ./migrations
COPY runtime-template/agent ./runtime-template/agent
USER operations
CMD ["uvicorn","operations.api:app","--host","0.0.0.0","--port","8000"]
