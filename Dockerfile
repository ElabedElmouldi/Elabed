
# استخدام نسخة خفيفة ومستقرة من بايثون
FROM python:3.10-slim

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# تثبيت الأدوات اللازمة للنظام (اختياري لضمان استقرار المكتبات)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# نسخ ملف المتطلبات أولاً للاستفادة من الـ Caching
COPY requirements.txt .

# تثبيت المكتبات البرمجية
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملف الكود الأساسي وبقية الملفات
COPY . .

# الأمر النهائي لتشغيل البوت
CMD ["python", "app.py"]
