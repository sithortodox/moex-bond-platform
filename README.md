# MOEX Bond Platform

Поиск и анализ облигаций Московской биржи с веб-интерфейсом Streamlit. Аналог dohod.ru/analytic/bonds и screener.cacao.services.

## Возможности

- **Сбор данных** — автоматическое получение информации по облигациям через API Московской биржи (ISIN, рейтинг, купон, YTM, цена, НКД, дюрация, объём торгов и др.) + импорт из Excel
- **Хранение** — PostgreSQL с 60+ полями, индексами и полнотекстовым поиском (pg_trgm)
- **Веб-интерфейс** — интерактивная таблица с фильтрами, сортировкой, поиском, настраиваемыми колонками и экспортом CSV
- **Автообновление** — ежедневный сбор данных по cron в 02:00
- **Продакшен** — systemd + Nginx reverse proxy с поддержкой WebSocket

## Архитектура

```
                          ┌──────────────┐
   MOEX API ───────────► │              │
   (iss.moex.com)        │  data_       │────────► PostgreSQL
                          │  collector   │          (moex_bonds)
   Excel (xlsx) ────────► │  .py         │
                          └──────┬───────┘
                                 │
                          ┌──────▼───────┐
                          │              │
   Браузер ◄── Nginx ◄── │ streamlit_   │
   (:80)       (:8501)    │ app.py       │
                          └──────────────┘
```

## Структура проекта

```
moex-bond-platform/
├── schema.sql              # Схема PostgreSQL (таблицы bonds, collection_log)
├── data_collector.py       # Сбор данных: MOEX API + импорт Excel → PostgreSQL
├── streamlit_app.py        # Веб-интерфейс Streamlit
├── requirements.txt        # Зависимости Python
├── .streamlit/
│   └── config.toml         # Конфигурация Streamlit
├── deploy.sh               # Автодеплой на VPS (запускать на сервере)
└── install.sh              # Self-contained инсталлятор (файлы в base64)
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

## Деплой на VPS с GitHub

### Шаг 1. Установить системные пакеты

```bash
apt-get update
apt-get install -y python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib nginx git curl
```

### Шаг 2. Клонировать репозиторий

```bash
git clone https://github.com/sithortodox/moex-bond-platform.git /opt/moex-bond-platform
```

### Шаг 3. Настроить PostgreSQL

```bash
systemctl enable --now postgresql

sudo -u postgres psql -c "CREATE USER moex WITH PASSWORD '${DB_PASSWORD:-moex123}';"
sudo -u postgres psql -c "CREATE DATABASE moex_bonds OWNER moex;"
sudo -u postgres psql -d moex_bonds -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

### Шаг 4. Применить схему БД

```bash
sudo -u postgres psql -d moex_bonds -f /opt/moex-bond-platform/schema.sql
```

### Шаг 5. Создать Python-окружение

```bash
python3.12 -m venv /opt/moex-bond-platform/venv
source /opt/moex-bond-platform/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/moex-bond-platform/requirements.txt
```

### Шаг 6. Импортировать начальные данные

Если есть Excel-файл с данными облигаций (лист `data`, 54 колонки):

```bash
/opt/moex-bond-platform/venv/bin/python3.12 \
    /opt/moex-bond-platform/data_collector.py /путь/к/файлу.xlsx
```

Или запустить сбор с API Мосбиржи (занимает 20+ минут):

```bash
/opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py
```

### Шаг 7. Настроить systemd

Создать `/etc/systemd/system/moex-bond-screener.service`:

```ini
[Unit]
Description=MOEX Bond Screener (Streamlit)
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/moex-bond-platform
Environment=DATABASE_URL=postgresql://moex:${DB_PASSWORD:-moex123}@localhost:5432/moex_bonds
Environment=PATH=/opt/moex-bond-platform/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/moex-bond-platform/venv/bin/streamlit run /opt/moex-bond-platform/streamlit_app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запустить:

```bash
systemctl daemon-reload
systemctl enable moex-bond-screener
systemctl start moex-bond-screener
```

### Шаг 8. Настроить Nginx

Создать `/etc/nginx/sites-available/moex-bond-screener`:

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

Активировать:

```bash
ln -sf /etc/nginx/sites-available/moex-bond-screener /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

### Шаг 9. Открыть порты

```bash
ufw allow 80/tcp
ufw allow 8501/tcp
```

### Шаг 10. Настроить ежедневное обновление

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py >> /var/log/moex-collector.log 2>&1") | crontab -
```

### Шаг 11. Открыть в браузере

```
http://ВАШ_IP/
```

---

## Быстрый деплой (одна команда)

Если репозиторий уже клонирован на сервер, запустите:

```bash
bash /opt/moex-bond-platform/deploy.sh
```

Скрипт автоматически выполнит шаги 1–10.

---

## SSL (Let's Encrypt)

Если есть домен, направленный на IP сервера:

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql://moex:${DB_PASSWORD:-moex123}@localhost:5432/moex_bonds` | Подключение к PostgreSQL |
| `MOEX_API_DELAY` | `1.2` | Задержка между запросами к MOEX API (секунды) |

Для изменения отредактируйте `Environment` в systemd-юните.

## Управление

```bash
systemctl status moex-bond-screener     # статус
systemctl restart moex-bond-screener    # перезапуск
journalctl -u moex-bond-screener -f     # логи Streamlit
tail -f /var/log/moex-collector.log     # логи сборщика

# Ручной сбор данных
/opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py

# Импорт Excel
/opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py /путь/к/файлу.xlsx
```

## Веб-интерфейс

### Таблица облигаций

- **Toggle колонок** — чекбоксы в боковой панели
- **Фильтры** — рейтинг, тип эмитента, валюта, тип купона, ликвидность, квалиф. инвестор
- **Числовые фильтры** — YTM, дюрация, цена, купон, объём торгов (слайдеры)
- **Сортировка** — выбор колонки + направление
- **Поиск** — по ISIN, названию, эмитенту
- **Экспорт** — скачивание CSV

### Доступные поля (54 колонки)

| Группа | Поля |
|--------|------|
| Идентификация | ISIN, Название, Эмитент, Основной заёмщик, SECID |
| Рейтинги | Рейтинг, Кредитное качество (рэнкинг, число), Качество эмитента |
| Доходность | YTM, YTM (MOEX), Простая, Текущая, Без реинвестирования, G-spread |
| Купон | Размер, %, Частота, Тип (фикс/плав), НКД |
| Сроки | Дата погашения, Лет до даты, Дюрация, Ближайшая дата, Событие |
| Цена | Цена % от номинала, Номинал, Мин. лот |
| Ликвидность | Объём 15д, Медиана оборота, Категория ликвидности |
| Эмитент | Тип, Страна, Отрасль, Субординир., Гарантия, Квалиф. инвестор |
| Прочее | Объём выпуска, Валюта, Дата выпуска, Оферты колл/пут, Амортизация |

## Схема базы данных

**Таблица `bonds`** — 60+ полей:

- Ключи: `id` (SERIAL), `isin` (UNIQUE)
- Индексы: ISIN, YTM, рейтинг, дюрация, цена, тип эмитента
- Trigram-индексы (GIN): name, issuer — для поиска по подстроке

**Таблица `collection_log`** — журнал сборов:

- started_at, finished_at, status (completed/failed)
- bonds_found, bonds_inserted, bonds_updated, errors

## Обновление

Для обновления до последней версии:

```bash
cd /opt/moex-bond-platform
git pull
pip install -r requirements.txt
systemctl restart moex-bond-screener
```

## Источник

Проект основан на [moex-bond-search-and-analysis](https://github.com/empenoso/moex-bond-search-and-analysis) и расширен:

- Хранение в PostgreSQL вместо Excel
- Веб-интерфейс Streamlit вместо CLI
- 54+ колонки из «карты рынка» dohod.ru
- Ежедневное автоматическое обновление
- Полнотекстовый поиск

## Лицензия

Apache-2.0
