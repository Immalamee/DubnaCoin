# Используем официальный образ Python в качестве базового
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем содержимое текущей директории в контейнер
COPY . /app

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Открываем порт 5000 для Flask
EXPOSE 5000

# Устанавливаем переменную окружения
ENV FLASK_APP=app.py

# Запускаем приложение
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
