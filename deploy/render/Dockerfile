# Hosted read-only demo on Render's free tier (D-037). Built from this repo; the prebuilt memory store,
# saved model replies and transcripts (AMI, CC BY 4.0) come from the repo's "demo-data-v1" release,
# so nothing is re-extracted or re-embedded and the service starts in seconds.
FROM python:3.11-slim

ARG DATA_BUNDLE=https://github.com/mithilyr/meeting-memory/releases/download/demo-data-v1/memory-bundle.tar.gz
WORKDIR /app
RUN pip install --no-cache-dir numpy==2.4.6 python-dotenv==1.0.1
COPY src ./src
RUN python -c "import urllib.request, tarfile; urllib.request.urlretrieve('${DATA_BUNDLE}', '/tmp/b.tgz'); \
tarfile.open('/tmp/b.tgz').extractall('/app', filter='data')" && rm /tmp/b.tgz && ls /app/.cache /app/data

# API keys are not in the image: add OPENROUTER_API_KEY, GROQ_API_KEY and VOYAGE_API_KEY in Render's
# Environment settings. Render sets PORT itself.
ENV HOST=0.0.0.0 READ_ONLY=1 MODEL_CALLS_PER_HOUR=20 DATA_PATH=/app/data CACHE_DIR=/app/.cache PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.ui.server"]
