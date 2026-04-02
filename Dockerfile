# استخدام نسخة مستقرة وتحتوي على أدوات البناء
FROM python:3.10

# تحديد مجلد العمل
WORKDIR /app

# تحديث pip و setuptools و wheel (ضروري جداً لـ pandas-ta)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# نسخ ملف المتطلبات وتثبيته
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية ملفات المشروع
COPY . .

# التأكد من تشغيل ملف app.py
CMD ["python", "app.py"]
