#!/usr/bin/env python3
import os
import asyncio

# Тут пишем токен бота и ID админа
BOT_TOKEN = "YOUR_BOT_TOKEN"  # Замените на ваш токен бота
ADMIN_IDS = "YOUR_ADMIN_IDS"  # Замените на ваши ID администраторов

# Переменные окружения
os.environ["BOT_TOKEN"] = BOT_TOKEN
os.environ["ADMIN_IDS"] = ADMIN_IDS

# Импортируем и запускаем основной модуль
from main import main

if __name__ == "__main__":
    asyncio.run(main())
