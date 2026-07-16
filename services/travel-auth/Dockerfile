FROM python:3.12-slim

WORKDIR /app/travel-auth

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY common ../common
COPY travel-auth/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY travel-auth/app ./app

EXPOSE 8300

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8300"]
