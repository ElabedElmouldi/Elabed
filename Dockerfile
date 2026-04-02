FROM python:3.10-slim

WORKDIR /app

# إضافة أدوات البناء الضرورية لـ pandas و numpy
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# تحديث pip قبل كل شيء
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]
