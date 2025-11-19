FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run נותן PORT בסביבת הריצה, נשתמש בו אם קיים
ENV PORT=8080

CMD ["uvicorn", "webhook_server:app", "--host", "0.0.0.0", "--port", "8080"]
# אפשר גם:
# CMD ["sh", "-c", "uvicorn webhook_server:app --host 0.0.0.0 --port ${PORT}"]
