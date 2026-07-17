FROM python:3.12-slim

WORKDIR /app/trip

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY common ../common
COPY trip/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY trip/app ./app

EXPOSE 8200

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
