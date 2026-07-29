# obsidian-agent — unified_bot runtime image.
# Minimal stack (finance + planning + agent + voice/ASR). Heavy knowledge
# ingest (OCR/vision) is intentionally out of scope for this image; add
# knowledge_bot/requirements.txt if you enable that domain.
FROM python:3.12-slim

# ffmpeg: Telegram voice -> ASR;  libgomp1: ctranslate2/onnxruntime (faster-whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
        rsync \
        openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    DEPLOY_MODE=single \
    AGENT_LOCALE=en

# Install deps first for layer caching.
COPY constraints.txt requirements-min.txt ./
COPY finance_bot/requirements.txt finance_bot/requirements.txt
RUN pip install --no-cache-dir -r requirements-min.txt -c constraints.txt

COPY . .

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# The vault is mounted at runtime; configuration comes from env / .env.
# VAULT_PATH, TELEGRAM_UNIFIED_BOT_TOKEN, DEEPSEEK_API_KEY are required.
CMD ["python", "-m", "unified_bot.main"]
