# Hosted read-only demo on Render's free tier (D-037). Built from this repo. A small public bundle on
# Hugging Face (8 MB: the memory store without its vectors, saved model replies, the transcripts; AMI,
# CC BY 4.0) is downloaded and its SHA-256 checked. The vectors (about 23,000) are re-embedded here, once
# per deploy, because the full 98 MB store would not upload over the build machine's connection.
FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir numpy==2.4.6 python-dotenv==1.0.1
COPY src ./src
COPY deploy/render/fetch_data.py /tmp/fetch_data.py
RUN python /tmp/fetch_data.py /app && rm /tmp/fetch_data.py /tmp/bundle.tgz

ENV HOST=0.0.0.0 READ_ONLY=1 MODEL_CALLS_PER_HOUR=20 DATA_PATH=/app/data CACHE_DIR=/app/.cache PYTHONUNBUFFERED=1

# Render passes the service's environment variables to the build as build args. Only the Voyage key is
# needed here (about 5 minutes of embedding calls); the answer-model keys are read at run time only.
ARG VOYAGE_API_KEY
RUN VOYAGE_API_KEY="$VOYAGE_API_KEY" python -c "from src.memory.store import connect, embed_missing, embed_events; \
from src.agent.route import update_profiles; c = connect(); \
print('chunks', embed_missing(c), 'events', embed_events(c), 'profiles', update_profiles(c))"

CMD ["python", "-m", "src.ui.server"]
