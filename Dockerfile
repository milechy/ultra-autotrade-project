# ─── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# ビルドツール（最終イメージには含めない）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

# wheel をビルド（キャッシュ効率化: requirements が変わった時だけ再ビルド）
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ─── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# ランタイム依存のみ（gcc 等のビルドツールは除外）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# builder の wheel をコピーしてインストール（ネットワーク不要）
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels /wheels/*.whl \
    && rm -rf /wheels

# アプリケーションコードをコピー
COPY backend/ backend/

# 本番用: Cythonコンパイル
ARG BUILD_MODE=development
RUN if [ "$BUILD_MODE" = "production" ]; then \
      pip install Cython && \
      cd /app/backend && python setup_cython.py build_ext --inplace && \
      find app/ai -name "*.py" ! -name "__init__.py" ! -name "schemas.py" ! -name "router.py" ! -name "decisions_router.py" ! -name "decisions_schemas.py" ! -name "models.py" -delete; \
    fi

# 非 root ユーザーで実行（docs/13_security_design.md）
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
