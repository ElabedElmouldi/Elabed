# استخدام نسخة مستقرة
FROM python:3.10-slim

# ضبط المجلد
WORKDIR /app

# تثبيت أدوات النظام الضرورية للبناء
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# تحديث pip وتثبيت wheel لضمان بناء المكتبات بسرعة
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# نسخ ملف المتطلبات وتثبيته
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# تشغيل الملف الأساسي
CMD ["python", "app.py"]
