# 1. استخدام نسخة بايثون خفيفة ومستقرة
FROM python:3.11-slim

# 2. تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# 3. تثبيت أدوات النظام الضرورية (إذا لزم الأمر)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملف المكتبات أولاً (للاستفادة من التخزين المؤقت/Cache)
COPY requirements.txt .

# 5. تثبيت المكتبات البرمجية
RUN pip install --no-cache-dir -r requirements.txt

# 6. نسخ باقي ملفات المشروع إلى الحاوية
COPY . .

# 7. تحديد المنفذ الذي سيعمل عليه Flask (رندر يستخدم 10000 افتراضياً)
ENV PORT=10000
EXPOSE 10000

# 8. أمر التشغيل باستخدام Gunicorn لضمان استقرار السيرفر
# ملاحظة: app:app تعني (اسم الملف هو app.py : واسم متغير Flask هو app)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app", "--timeout", "120"]
