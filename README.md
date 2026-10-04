<h1 align="center">Starvell Assistant</h1>
<h4 align="center">Простой и эффективный бот для автоматизации Starvell</h4>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python"></a>
  <a href="https://github.com/aiogram/aiogram"><img src="https://img.shields.io/badge/aiogram-v3.x-2CA5E0.svg" alt="aiogram"></a>
  <a href="https://github.com/gadacy"><img src="https://img.shields.io/badge/Author-gadacy-brightgreen.svg" alt="Author"></a>
  <a href="https://t.me/StarAssis"><img src="https://img.shields.io/badge/%D0%A7%D0%B0%D1%82-@StarAssis-blue.svg" alt="Telegram Chat"></a>
  <a href="https://t.me/starvell_assistant"><img src="https://img.shields.io/badge/%D0%9A%D0%B0%D0%BD%D0%B0%D0%BB-@starvell__assistant-blue.svg" alt="Telegram Channel"></a>
  <a href="https://t.me/StarPlugin"><img src="https://img.shields.io/badge/%D0%9F%D0%BB%D0%B0%D0%B3%D0%B8%D0%BD%D1%8B-@StarPlugin-blue.svg" alt="Telegram Plugins"></a>
  <a href="https://t.me/addlist/QmOelFMfLqE0MWEy"><img src="https://img.shields.io/badge/Telegram-%D0%9F%D0%B0%D0%BF%D0%BA%D0%B0_%D1%87%D0%B0%D1%82%D0%BE%D0%B2-2CA5E0.svg" alt="Telegram Folder"></a>
  <a href="https://bhost.fun/r/starassis"><img src="https://img.shields.io/badge/%D0%A5%D0%BE%D1%81%D1%82%D0%B8%D0%BD%D0%B3-BHost_(--5%25)-orange.svg" alt="Хостинг BHost"></a>
</p>

<h2 align="center">Перед началом настоятельно рекомендую залететь в наш <a href="https://t.me/StarAssis">Telegram
чат (клик)</a>. Тут и поможем чем сможем и посидеть можно.</h2>
<p align="center">
  📁 <b><a href="https://t.me/addlist/QmOelFMfLqE0MWEy">Добавить папку со всеми чатами и каналами проекта в Telegram (клик)</a></b>
</p>

## :clipboard: **Содержание**

- [Возможности](#robot-возможности)
    - [Starvell](#shopping_cart-starvell)
    - [Уведомления и ПУ в Telegram](#left_speech_bubble-уведомления-и-пу-в-telegram)
    - [Дополнительные возможности](#gear-дополнительные-возможности)

- [Преимущества](#1st_place_medal-преимущества)
    - [Для пользователей](#grinning-для-пользователей)
    - [Для разработчиков](#computer-для-разработчиков)

- [Плагины](#electric_plug-плагины)
- [Хостинг](#cloud-хостинг)
- [Установка](#arrow_down-установка)
    - [Windows](#large_blue_diamond-windows)
    - [Linux (Ubuntu)](#hotsprings-linux-ubuntu)
    - [Docker](#whale-docker)
- [Установка плагинов](#electric_plug-установка-плагинов)
- [Мне нужна помощь](#question-мне-нужна-помощь)
- [Star it](#star-star-it)

## :robot: **Возможности**

### :shopping_cart: **Starvell**

- Автовыдача товаров.
- Автоподнятие лотов.
- Автоответ на заготовленные команды.
- Быстрые ответы (Quick Replies).
- Автоматические напоминания об отзывах.
- Вечный онлайн.
- Уведомления в телеграм.
- Полноценная ПУ в Telegram.

### :left_speech_bubble: **Уведомления и ПУ в Telegram**

- Возможность установки нескольких чатов для уведомлений.
- Уведомления о поднятии лотов.
- Уведомления о новых заказах.
- Уведомления о выдаче товара.
- Уведомления о новых сообщениях.
- Уведомления об отзывах.
- Возможность отвечать на сообщения прямо из Telegram (через ответ на сообщение или в режиме диалога).
- Возможность полностью настраивать автовыдачу / автоответчик / автоподнятие и все остальные модули бота через Telegram.
- Возможность управлять запасами товаров и ключей прямо из Telegram.

### :gear: **Дополнительные возможности**

- Использование переменных в тексте для автоответа / автовыдачи.
- Создание плагинов для кастомизации функционала без редактирования исходного кода самого бота.
- Автоматическое отключение приветствий и автоответов для покупателей с активным заказом.

## :1st_place_medal: **Преимущества**

### :grinning: **Для пользователей**

- **Больше**, чем наличие самого нужного функционала.
- **Оптимизация**. _20 МБ свободного места на диске, до 50 МБ ОЗУ, доступ в интернет_ — все что нужно для работы.
- Возможность установить на **любую платформу**, которую поддерживает _Python: Windows, Linux, Docker_ и т.д.
- Возможность установки плагинов дает **огромную вариативность** модификации стандартного функционала под самые разные нужды.
- Простое и надежное хранение данных (SQLite).
- Постоянные обновления, быстрое реагирование на баги / предложения о новом функционале.
- Полное управление через Telegram.

### :computer: **Для разработчиков**

- Выбран самый простой и при этом один из самых мощных языков для такого рода приложений — _Python_ (3.10+).
- Использование современного асинхронного стека: _aiogram 3.x_, _SQLAlchemy 2.0 (asyncio)_, _httpx_.
- Полная документация кода, type-хинты и строгая типизация (Pydantic).
- Широкое использование ООП. Почти каждый эвент / сообщение / заказ представляют собой экземпляр соответствующего класса.
- Возможность легкого создания плагинов.
- Сконфигурированный логгер. Никаких принтов!
- Набор готовых регрессионных тестов (`regression_checks.py`, `chat_regression_checks.py`, `next_data_regression_checks.py`).

## :electric_plug: Плагины

- [Канал с плагинами](https://t.me/StarPlugin)

## :cloud: Хостинг

Для круглосуточной и стабильной работы бота 24/7 (чтобы не держать собственный ПК постоянно включенным) рекомендуется использовать хостинг **[BHost](https://bhost.fun/r/starassis)**.

> 🎁 **Скидка 5%**: переходите и регистрируйтесь по реферальной ссылке **[bhost.fun/r/starassis](https://bhost.fun/r/starassis)**, чтобы получить скидку 5% на услуги хостинга!

### Почему BHost отлично подходит для Starvell Assistant:
- **Автоустановка в один клик**: не нужно вручную настраивать сервер и ставить зависимости — при оформлении сервера в выборе ПО выберите категорию **Starvell**, а в ней — **Starvell Assistant**, и всё установится автоматически!
- **Ультрабюджетные тарифы для ботов**: линейка тарифов *Coding* разработана специально для скриптов и ботов. Цены стартуют всего от **39 ₽/месяц**, что с запасом перекрывает системные требования бота (требуется всего от 20 МБ диска и до 50 МБ ОЗУ).
- **Бесперебойная работа 24/7**: бот будет круглосуточно находиться в сети, автоподнимать лоты, мгновенно отправлять ответы и выдавать заказы без задержек.
- **DDoS-защита и скорость**: надежная защита от DDoS-атак, низкий пинг и канал 1 Гбит/с.
- **Производительное железо**: быстрые NVMe-накопители и современные серверные процессоры.
- **Удобство**: простая панель управления и оперативная техподдержка 24/7.

## :arrow_down: Установка

> 💡 **Самый быстрый способ**: на хостинге **[BHost](https://bhost.fun/r/starassis)** доступна готовая автоустановка — при выборе ПО укажите категорию **Starvell** ➔ **Starvell Assistant**.

### :large_blue_diamond: Windows

1. Скачайте и установите [Python 3.10+](https://www.python.org/downloads/).
    1. При установке поставьте галочку у `Add python.exe to PATH` на первом экране установки.
2. Скачайте [Starvell Assistant](https://github.com/gadacy/starvell-assistant/archive/refs/heads/main.zip) и распакуйте архив, либо склонируйте репозиторий:
   ```bash
   git clone https://github.com/gadacy/starvell-assistant.git
   cd starvell-assistant
   ```
3. Создайте и активируйте виртуальное окружение:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
4. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
5. Запустите бота (мастер настройки запустится прямо в этом же окне, если конфиг отсутствует или повреждён):
   ```bash
   python main.py
   ```
   *(при желании вы также можете запустить мастер отдельно через `python setup.py` или заполнить `.env` и `config.json` вручную)*.

### :hotsprings: Linux (Ubuntu)

1. Обновите пакеты и установите Python, venv и git:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
   ```
2. Склонируйте репозиторий и перейдите в папку:
   ```bash
   git clone https://github.com/gadacy/starvell-assistant.git
   cd starvell-assistant
   ```
3. Создайте виртуальное окружение и установите библиотеки:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Запустите бота (мастер первоначальной настройки запустится прямо в консоли при первом старте или повреждении конфига):
   ```bash
   python3 main.py
   ```
   *(для постоянной работы в фоне на сервере используйте `systemd`, `screen` или `tmux`. Также доступен отдельный запуск мастера: `python3 setup.py`)*.

### :whale: Docker

1. Установите [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) или Docker Engine + Docker Compose (Linux) и запустите его.
2. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/gadacy/starvell-assistant.git
   cd starvell-assistant
   ```
3. Настройте конфигурационные файлы (`.env` и `config.json`):
   ```bash
   cp .env.example .env
   cp config.json.example config.json
   ```
4. Запустите бота в фоне:
   ```bash
   docker compose up -d --build
   ```
5. Полезные команды:
   - Логи: `docker compose logs -f`
   - Перезапуск: `docker compose restart`
   - Остановить: `docker compose down`

## :electric_plug: Установка плагинов

Не устанавливайте плагины из непроверенных источников. Через систему плагинов злоумышленники могут получить полный доступ к Вашему устройству или аккаунту Starvell. Установка плагинов крайне проста:

1. Введите команду `/menu` (или `/plugins`) в диалоге с ботом Telegram.
2. Нажмите кнопку `🧩 Плагины`.
3. Нажмите кнопку `➕ Добавить плагин`.
4. Отправьте или перешлите боту файл плагина с расширением `.py`.

## :question: Мне нужна помощь

Если у вас остались какие-либо вопросы, мы с радостью ответим на них в нашем сообществе:

- 💬 **Telegram чат:** [@StarAssis](https://t.me/StarAssis)
- 📢 **Канал проекта:** [@starvell_assistant](https://t.me/starvell_assistant)
- 🧩 **Канал с плагинами:** [@StarPlugin](https://t.me/StarPlugin)
- 📁 **Все ресурсы разом:** [Добавить папку в Telegram](https://t.me/addlist/QmOelFMfLqE0MWEy)

## :star: Star it

Если вам удобно пользоваться Starvell Assistant, не забудьте поставить :star: звезду :star: данному проекту в правом верхнем углу GitHub-страницы (нужно быть авторизованным в свой аккаунт) :)
