FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser
CMD ["python", "main.py"]