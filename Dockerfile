FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY product_app/requirements.txt product_app/requirements-app.txt ./product_app/
RUN pip install --no-cache-dir -r product_app/requirements.txt -r product_app/requirements-app.txt

COPY . .
RUN chmod +x product_app/start_hosted.sh

ENV PORT=8502 \
    API_PORT=8000 \
    API_BASE_URL=http://127.0.0.1:8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl --fail http://127.0.0.1:8502/_stcore/health || exit 1

CMD ["bash", "product_app/start_hosted.sh"]
