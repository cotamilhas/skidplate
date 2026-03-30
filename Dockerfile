FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m botuser && mkdir -p api_logs && chown -R botuser:botuser /app
USER botuser
CMD ["python", "main.py"]