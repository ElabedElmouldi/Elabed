FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# هذا هو البديل لـ Procfile في نظام Docker
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]


