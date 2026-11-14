# Hosted read-only demo on Hugging Face Spaces (D-037). Built from the folder deploy/build_space.py stages:
# the code, the 138 transcripts (AMI, CC BY 4.0), the prebuilt memory store and the saved model replies.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
WORKDIR /app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .

# API keys are not in the image: add OPENROUTER_API_KEY, GROQ_API_KEY and VOYAGE_API_KEY as Space secrets.
ENV HOST=0.0.0.0 PORT=7860 READ_ONLY=1 MODEL_CALLS_PER_HOUR=20 \
    DATA_PATH=/app/data CACHE_DIR=/app/.cache PYTHONUNBUFFERED=1
USER user
EXPOSE 7860
CMD ["python", "-m", "src.ui.server"]
