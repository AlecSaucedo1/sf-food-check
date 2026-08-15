FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x ./run.sh ./scripts/sync_datasf.py

# Fetch, normalize, score and validate all official DataSF inspection eras while the
# new image is being built. If any source is unavailable or coverage validation
# fails, the deployment fails before Render replaces the currently serving instance.
RUN python scripts/build_complete_bundle.py

EXPOSE 8000
CMD ["./run.sh"]
