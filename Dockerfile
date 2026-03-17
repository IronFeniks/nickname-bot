FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

# Создаем директорию для данных (на всякий случай)
RUN mkdir -p /data

# Запускаем бота
CMD ["python", "bot.py"]
