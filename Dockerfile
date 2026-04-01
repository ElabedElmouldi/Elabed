FROM python:3.10-slim

# تحديد مسار العمل
WORKDIR /app

# نسخ ملف المكتبات أولاً لتسريع البناء
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية الملفات
COPY . .

# تشغيل البوت (استخدمنا gunicorn للأداء الاحترافي)
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]
