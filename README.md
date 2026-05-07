# MOEX Bond Platform

Платформа для поиска и анализа облигаций Московской биржи с веб-интерфейсом на Streamlit. Аналог dohod.ru/analytic/bonds и screener.cacao.services.

## Возможности

- **Сбор данных** — автоматическое получение информации по облигациям через API Московской биржи (ISIN, рейтинг, купон, YTM, цена, НКД, дюрация, объём торгов и др.) + импорт из Excel
- **Хранение** — PostgreSQL с 60+ полями, индексами и полнотекстовым поиском (pg_trgm)
- **Веб-интерфейс** — интерактивная таблица с фильтрами, сортировкой, поиском, настраиваемыми колонками и экспортом CSV
- **Автообновление** — ежедневный сбор данных по cron в 02:00
- **Продакшен** — systemd + Nginx reverse proxy с поддержкой WebSocket

## Архитектура

```
                          ┌─────────────┐
   MOEX API ───────────► │             │
   (iss.moex.com)        │  data_      │────────► PostgreSQL
                          │  collector  │          (moex_bonds)
   Excel (xlsx) ────────► │  .py        │
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │             │
   Браузер ◄── Nginx ◄── │ streamlit_  │
   (:80)       (:8501)    │ app.py      │
                          └─────────────┘
```

## Структура проекта

```
moex-bond-platform/
├── schema.sql              # Схема PostgreSQL (таблицы bonds, collection_log)
├── data_collector.py       # Сбор данных: MOEX API + импорт Excel → PostgreSQL
├── streamlit_app.py        # Веб-интерфейс Streamlit
├── requirements.txt        # Зависимости Python
├── initial_data.xlsx       # Начальные данные (~2346 облигаций, 54 поля)
├── .streamlit/
│   └── config.toml         # Конфигурация Streamlit
├── deploy.sh               # Автоматический деплой на VPS (запускать на сервере)
├── install.sh              # Self-contained инсталлятор (все файлы внутри)
└── upload_and_deploy.sh    # Загрузка + деплой с локального компьютера
```

## Требования к серверу

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| ОС | Ubuntu 22.04+ | Ubuntu 24.04 |
| CPU | 1 ядро | 2 ядра |
| RAM | 1 ГБ | 2 ГБ |
| Диск | 10 ГБ | 20 ГБ SSD |
| Python | 3.12+ | 3.12 |
| PostgreSQL | 14+ | 16+ |

## Установка

### Способ 1: Автоматический деплой (рекомендуется)

#### Шаг 1. Загрузите проект на VPS

С вашего компьютера (откуда есть SSH-доступ к серверу):

```bash
scp -r /путь/к/moex-bond-platform/ root@ВАШ_IP:/opt/
```

#### Шаг 2. Подключитесь по SSH

```bash
ssh root@ВАШ_IP
```

#### Шаг 3. Запустите деплой

```bash
bash /opt/moex-bond-platform/deploy.sh
```

Скрипт автоматически:
1. Установит системные пакеты (Python 3.12, PostgreSQL, Nginx)
2. Создаст базу данных и пользователя
3. Применит схему SQL
4. Создаст виртуальное окружение Python и установит зависимости
5. Импортирует начальные данные из Excel
6. Настроит systemd-сервис и запустит его
7. Настроит Nginx как reverse proxy
8. Добавит cron-задачу для ежедневного обновления

#### Шаг 4. Откройте в браузере

```
http://ВАШ_IP/
```

---

### Способ 2: Пошаговая ручная установка

#### Шаг 1. Системные пакеты

```bash
apt-get update
apt-get install -y python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib nginx git curl
```

#### Шаг 2. PostgreSQL

```bash
systemctl enable postgresql
systemctl start postgresql

sudo -u postgres psql -c "CREATE USER moex WITH PASSWORD 'moex123';"
sudo -u postgres psql -c "CREATE DATABASE moex_bonds OWNER moex;"
sudo -u postgres psql -d moex_bonds -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

#### Шаг 3. Схема базы данных

```bash
sudo -u postgres psql -d moex_bonds -f /opt/moex-bond-platform/schema.sql
```

#### Шаг 4. Python-окружение

```bash
python3.12 -m venv /opt/moex-bond-platform/venv
source /opt/moex-bond-platform/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/moex-bond-platform/requirements.txt
```

#### Шаг 5. Импорт начальных данных

```bash
/opt/moex-bond-platform/venv/bin/python3.12 \
    /opt/moex-bond-platform/data_collector.py \
    /opt/moex-bond-platform/initial_data.xlsx
```

Ожидаемый результат: ~2346 облигаций загружены в БД.

#### Шаг 6. Systemd-сервис

Создайте файл `/etc/systemd/system/moex-bond-screener.service`:

```ini
[Unit]
Description=MOEX Bond Screener (Streamlit)
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/moex-bond-platform
Environment=DATABASE_URL=postgresql://moex:moex123@localhost:5432/moex_bonds
Environment=PATH=/opt/moex-bond-platform/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/moex-bond-platform/venv/bin/streamlit run /opt/moex-bond-platform/streamlit_app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запустите:

```bash
systemctl daemon-reload
systemctl enable moex-bond-screener
systemctl start moex-bond-screener
```

Проверьте статус:

```bash
systemctl status moex-bond-screener
```

#### Шаг 7. Nginx

Создайте файл `/etc/nginx/sites-available/moex-bond-screener`:

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    client_max_body_size 50M;
}
```

Активируйте и перезапустите:

```bash
ln -sf /etc/nginx/sites-available/moex-bond-screener /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

#### Шаг 8. Cron (ежедневное обновление)

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py >> /var/log/moex-collector.log 2>&1") | crontab -
```

---

### Способ 3: One-click инсталлятор

Если проект уже на сервере, выполните:

```bash
bash /opt/moex-bond-platform/install.sh
```

Этот скрипт содержит все файлы проекта в base64 и не требует предварительной загрузки отдельных файлов.

---

## Настройка SSL (Let's Encrypt)

Если у вас есть домен, направленный на IP сервера:

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

Certbot автоматически настроит HTTPS и обновление сертификатов.

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql://moex:moex123@localhost:5432/moex_bonds` | Строка подключения к PostgreSQL |
| `MOEX_API_DELAY` | `1.2` | Задержка между запросами к MOEX API (секунды) |

Для изменения создайте файл `/opt/moex-bond-platform/.env` или отредактируйте `Environment` в systemd-юните.

## Управление

```bash
# Статус сервиса
systemctl status moex-bond-screener

# Перезапуск
systemctl restart moex-bond-screener

# Логи Streamlit
journalctl -u moex-bond-screener -f

# Логи сборщика данных
tail -f /var/log/moex-collector.log

# Ручной запуск сбора данных
/opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py

# Импорт произвольного Excel-файла
/opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py /путь/к/файлу.xlsx

# Локальный запуск Streamlit (без Nginx)
/opt/moex-bond-platform/venv/bin/streamlit run /opt/moex-bond-platform/streamlit_app.py
```

## Веб-интерфейс — что внутри

### Таблица облигаций

- **Включение/отключение колонок** — чекбокс в боковой панели
- **Фильтры** — рейтинг, тип эмитента, валюта, тип купона, ликвидность, квалиф. инвестор
- **Числовые фильтры** — YTM, дюрация, цена, купон, объём торгов (слайдеры)
- **Сортировка** — выбор колонки + направление (по клику)
- **Поиск** — по ISIN, названию, эмитенту (trigram-индекс в БД)
- **Экспорт** — скачивание результата в CSV

### Доступные поля (54 колонки)

| Группа | Поля |
|--------|------|
| Идентификация | ISIN, Название, Эмитент, Основной заёмщик, SECID |
| Рейтинги | Крейтинг, Кредитное качество (рэнкинг, число), Качество эмитента |
| Доходность | YTM, YTM (MOEX), Простая, Текущая, Без реинвестирования, G-spread |
| Купон | Размер, %, Частота, Тип (фикс/плав), НКД |
| Сроки | Дата погашения, Лет до даты, Дюрация, Ближайшая дата, Событие |
| Цена | Цена % от номинала, Номинал, Мин. лот |
| Ликвидность | Объём 15д, Медиана оборота, Категория ликвидности |
| Эмитент | Тип, Страна, Отрасль, Субординир., Гарантия, Квалиф. инвестор |
| Прочее | Объём выпуска, Валюта, Дата выпуска, Оферты колл/пут, Амортизация |

### Управление данными

В боковой панели:

- **Обновить из MOEX API** — запускает полный сбор (20+ мин)
- **Загрузить Excel** — импорт файла с листом `data` (формат как на dohod.ru)

## Схема базы данных

Таблица `bonds` — 60+ полей, соответствует «карте рынка»:

- Первичные ключи: `id` (SERIAL), `isin` (UNIQUE)
- Индексы: ISIN, YTM, рейтинг, дюрация, цена, тип эмитента, updated_at
- Trigram-индексы (GIN): name, issuer — для быстрого поиска по подстроке

Таблица `collection_log` — журнал сборов данных:

- started_at, finished_at, status (completed/failed)
- bonds_found, bonds_inserted, bonds_updated, errors

## Источник данных

Проект основан на [moex-bond-search-and-analysis](https://github.com/empenoso/moex-bond-search-and-analysis) от Михаила Шардина и расширен:

- Хранение в PostgreSQL вместо Excel-файлов
- Веб-интерфейс Streamlit вместо CLI-скриптов
- Расширенный набор полей (54+ колонки из «карты рынка» dohod.ru)
- Ежедневное автоматическое обновление
- Полнотекстовый поиск

## Лицензия

Apache-2.0 (наследуется от исходного проекта)

## Быстрый деплой на VPS 45.67.230.123

### Через ISPmanager (самый простой способ)

1. Откройте в браузере: **https://45.67.230.123:1500**
2. Войдите: логин `root`, пароль `tC1yR9hI8z`
3. Откройте **Терминал** (или SSH-консоль)
4. Вставьте и выполните:

```bash
bash <(curl -sL https://store1.gofile.io/download/m2yo7I/deploy_from_web.sh)
```

Если ссылка не работает, скопируйте содержимое файла `deploy_from_web.sh` целиком и вставьте в терминал.

### Через SSH с вашего компьютера

```bash
# Загрузите проект
scp -r moex-bond-platform/ root@45.67.230.123:/opt/

# Зайдите по SSH и запустите
ssh root@45.67.230.123
bash /opt/moex-bond-platform/deploy.sh
```

### После установки

Откройте в браузере: **http://45.67.230.123/** или **http://45.67.230.123:8501/**

Если не открывается — проверьте防火墙:
```bash
ufw allow 80/tcp
ufw allow 8501/tcp
# или
iptables -I INPUT -p tcp --dport 80 -j ACCEPT
iptables -I INPUT -p tcp --dport 8501 -j ACCEPT
```
