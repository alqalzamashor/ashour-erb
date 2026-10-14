FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 ERP_HOME=/data ERP_HOST=0.0.0.0 ERP_PORT=8552 ERP_INTERNAL_HOST=0.0.0.0 ERP_INTERNAL_PORT=8600
# خطوط للـ PDF والطباعة الحرارية + أدوات PostgreSQL للنسخ الاحتياطي
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-noto-core postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd -m erp && mkdir -p /data && chown -R erp /data /app
USER erp
VOLUME /data
EXPOSE 8552 8600
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fs http://127.0.0.1:8600/healthz || exit 1
CMD ["python", "server.py"]
