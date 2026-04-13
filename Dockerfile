# =========================
# PRO AI TRADING BOT
# =========================

FROM python:3.11-slim

# تحسين الأداء والاستقرار
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONFAULTHANDLER=1

# مجلد العمل
WORKDIR /app

# تثبيت أدوات النظام (مهم للـ AI + pandas + ta)
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# نسخ المشروع
COPY . /app

# تحديث pip
RUN pip install --no-cache-dir --upgrade pip

# تثبيت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# فتح منفذ (Flask / Keep alive)
EXPOSE 8080

# تشغيل البوت
CMD ["python", "-u", "app.py"]
