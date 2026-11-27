FROM python:3.14-slim

WORKDIR /app
RUN pip install --no-cache-dir "Flask>=3.1,<4" "requests>=2.32,<3" "gunicorn>=23,<24"
COPY app.py .
USER 65534:65534
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "app:app"]
