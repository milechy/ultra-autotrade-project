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

# アプリケーションコードをコピー（Cythonビルドのために必要）
COPY backend/ backend/

# 本番用: Cythonコンパイル（builderステージで実行 - gccが利用可能）
ARG BUILD_MODE=development
RUN if [ "$BUILD_MODE" = "production" ]; then \
      pip install --no-index --find-links /wheels Cython && \
      cd /build/backend && python setup_cython.py build_ext --inplace; \
    fi


# ─── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# ランタイム依存のみ（gcc 等のビルドツールは除外）
# apt-get upgrade でOS層のセキュリティパッチを適用（Trivy CVE修正）
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# builder の wheel をコピーしてインストール（ネットワーク不要）
COPY --from=builder /wheels /wheels
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --no-index --find-links /wheels /wheels/*.whl \
    && rm -rf /wheels

# アプリケーションコードをコピー（Cythonコンパイル済み成果物を含む）
COPY --from=builder /build/backend/ backend/

# 本番用: Cythonコンパイル済みの場合、元の.pyファイルを削除（.soで代替）
ARG BUILD_MODE=development
RUN if [ "$BUILD_MODE" = "production" ]; then \
      find backend/app/ai -name "*.py" ! -name "__init__.py" ! -name "schemas.py" ! -name "router.py" ! -name "decisions_router.py" ! -name "decisions_schemas.py" ! -name "models.py" -delete; \
    fi

# 非 root ユーザーを作成（docs/13_security_design.md）
# UID/GID は 10001 で固定。docker-compose の backend-volume-init と
# entrypoint.sh の chown 対象 UID と一致させる必要がある。
RUN groupadd --gid 10001 appuser \
    && useradd --no-create-home --shell /bin/false --uid 10001 --gid 10001 appuser
# イメージ層でもディレクトリを作成しておく（新規 volume の初回 population 時に
# chown 済み状態でコピーされる）。
RUN mkdir -p /var/log/ultra-autotrade /var/run/ultra \
    && chown appuser:appuser /var/log/ultra-autotrade /var/run/ultra

# entrypoint: root で起動 → named volume を chown → gosu で appuser に降格して CMD を exec
# USER appuser は設定しない（entrypoint が権限降格を担う）
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
