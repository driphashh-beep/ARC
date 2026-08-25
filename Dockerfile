FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ARC_ENV=production ARC_PORT=3132 ARC_BIND=0.0.0.0
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data && useradd --create-home arc && chown -R arc:arc /app
USER arc
EXPOSE 3132
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3132/health', timeout=3)"
CMD ["python", "arc.py"]
