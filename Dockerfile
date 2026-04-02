
# استخدام نسخة بايثون مستقرة وخفيفة
FROM python:3.11-slim

# تحديد مجلد العمل
WORKDIR /app

# تثبيت الأدوات الأساسية لنظام التشغيل إذا لزم الأمر
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# نسخ وتثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملفات المشروع
COPY . .

# تعيين المنفذ الافتراضي
ENV PORT=10000
EXPOSE 10000

# تشغيل التطبيق باستخدام Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]


