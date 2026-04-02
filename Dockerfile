FROM python:3.10-slim

# تحديد مجلد العمل
WORKDIR /app

# تثبيت أدوات النظام الضرورية لبناء المكتبات (مهم لـ pandas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# تحديث pip لضمان العثور على أحدث المكتبات
RUN pip install --upgrade pip

# نسخ ملف المتطلبات وتثبيته
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية الملفات
COPY . .

# تشغيل البوت
CMD ["python", "app.py"]
