FROM python:3.12.9-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MODEL_DIR=/app/artifacts
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app --home /app app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY frontend ./frontend
COPY churn.csv ./churn.csv
RUN python -m app.model --data churn.csv --output artifacts && rm churn.csv && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=2)" || exit 1
CMD ["uvicorn","app.api:app","--host","0.0.0.0","--port","8000","--workers","1"]
