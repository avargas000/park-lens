FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DATABASE_PATH=/data/parks.db \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY applications ./applications
COPY components ./components
COPY bin ./bin
RUN chmod +x bin/start-all.sh \
    && useradd --create-home parklens && mkdir -p /data && chown parklens /data
USER parklens
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["bin/start-all.sh"]
