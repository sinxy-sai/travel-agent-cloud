FROM python:3.12-slim

WORKDIR /app/travel-gateway

COPY common ../common
COPY travel-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY travel-gateway/app ./app

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
