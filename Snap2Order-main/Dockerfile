FROM python:3.12-slim
WORKDIR /app
COPY server.py dish_media.py tls_support.py ocr_cloud.py wechat.py schema.sql ./
COPY vendor/ ./vendor/
COPY static/ ./static/
RUN useradd --uid 10001 --create-home appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser
ENV HOST=0.0.0.0 PORT=8765 DATABASE_PATH=/data/snap2order.sqlite3
EXPOSE 8765
CMD ["python", "server.py"]
