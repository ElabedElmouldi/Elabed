# استخدام نسخة بايثون 3.12 المتوافقة مع المكتبات الحديثة
FROM python:3.12-slim

WORKDIR /app

# تثبيت الأدوات اللازمة لبناء المكتبات البرمجية
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
