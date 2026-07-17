FROM python:3.12-slim

WORKDIR /app/agent

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY common ../common
COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/app ./app

EXPOSE 8400

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8400"]
