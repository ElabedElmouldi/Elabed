FROM python:3.11-slim

WORKDIR /app

# تثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# أمر التشغيل الصحيح (app:app تعني ملف app.py وكائن app)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
