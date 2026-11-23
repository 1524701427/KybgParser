# syntax=docker/dockerfile:1

# 基础镜像提供 Python、.NET 8、Java 和文档处理所需的系统库。
ARG BASE_IMAGE=docker.wh-ge.com/document-processing-base:1.0
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="WordParser" \
      org.opencontainers.image.description="Word/PDF report parsing API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai \
    DOTNET_ROOT=/usr/share/dotnet \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=false \
    JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8" \
    TMPDIR=/tmp/word-parser \
    HOME=/home/appuser \
    XDG_CACHE_HOME=/home/appuser/.cache \
    UVICORN_WORKERS=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY word_parser/ ./word_parser/
COPY configs/ ./configs/
COPY runtime/ ./runtime/
COPY runtime/runtimeconfig.linux.json ./runtime/runtimeconfig.json

# 基础镜像已提供系统库，此处只安装项目的 Python 依赖。
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

RUN set -eu; \
    command -v java >/dev/null; \
    command -v dotnet >/dev/null; \
    for file in Aspose.Words.dll Aspose.Total.NET.lic SkiaSharp.dll libSkiaSharp.so runtimeconfig.json; do \
        test -f "/app/runtime/$file" || { echo "Missing runtime file: $file" >&2; exit 1; }; \
    done; \
    python -c "import word_parser.application.http_api, fitz, opendataloader_pdf, rapidocr; print('Imports OK')"; \
    python -c "from word_parser.document.word.aspose_loader import AsposeWordsLoader; assert AsposeWordsLoader(fallback_to_simple=False)._load_aspose_runtime() is not None, 'Aspose.Words failed to load'"

RUN set -eu; \
    if ! id -u appuser >/dev/null 2>&1; then \
        if command -v useradd >/dev/null 2>&1; then \
            useradd --create-home --uid 10001 appuser; \
        else \
            adduser -D -u 10001 appuser; \
        fi; \
    fi; \
    mkdir -p /tmp/word-parser /home/appuser/.cache /app/data/predictions /app/tests; \
    chown -R appuser:appuser /app /tmp/word-parser /home/appuser

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn word_parser.application.http_api:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
