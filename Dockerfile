# ---- builder: 构建前端 ----
FROM node:22-alpine AS builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime: 运行后端 ----
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SEARCHHUB_WEB_DIST=/app/web/dist \
    SEARCHHUB_HOST=0.0.0.0 \
    SEARCHHUB_PORT=8000
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install . --no-cache-dir
COPY --from=builder /build/frontend/dist /app/web/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
CMD ["python", "-m", "searchhub"]
