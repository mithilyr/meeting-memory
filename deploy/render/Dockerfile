# Hosted read-only demo on Render's free tier (D-037). Built from this repo; the prebuilt memory store,
# saved model replies and transcripts (AMI, CC BY 4.0) come from a public Hugging Face dataset
# (deploy/render/fetch_data.py checks its SHA-256), so nothing is re-extracted or re-embedded and the
# service starts in seconds.
FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir numpy==2.4.6 python-dotenv==1.0.1
COPY src ./src
COPY deploy/render/fetch_data.py /tmp/fetch_data.py
RUN python /tmp/fetch_data.py /app && rm /tmp/fetch_data.py /tmp/bundle.tgz

# API keys are not in the image: add OPENROUTER_API_KEY, GROQ_API_KEY and VOYAGE_API_KEY in Render's
# Environment settings. Render sets PORT itself.
ENV HOST=0.0.0.0 READ_ONLY=1 MODEL_CALLS_PER_HOUR=20 DATA_PATH=/app/data CACHE_DIR=/app/.cache PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.ui.server"]
