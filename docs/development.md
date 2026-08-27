# Разработка

Envelope — небольшое серверное приложение на FastAPI. HTML отрисовывается на сервере, данные хранятся через SQLAlchemy, а схема базы обновляется Alembic.

## Локальный запуск

Нужны Python 3.14 и Poetry:

```bash
poetry install
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload
```

Основная страница для проверки:

```text
http://127.0.0.1:8000/users/1/envelopes/page
```

Для контейнерного запуска используется:

```bash
docker compose up --build
```

Compose сначала применяет миграции, затем запускает приложение. SQLite хранится в постоянном Docker volume.

## Структура

- `src/orm/` — модели пользователей, конвертов, операций и расходов.
- `src/envelope/` — бизнес-логика и маршруты API/HTML.
- `src/template/` и `src/static/` — серверные шаблоны и интерфейс.
- `migrations/` — текущая базовая миграция схемы.
- `tests/` — тесты приложения.

Модели используют простой Active Record-подход для основных операций с данными.

## Проверки

```bash
poetry run pytest
poetry run ruff check .
poetry run mypy src
```

Визуальные решения и структуру интерфейса сверяем с [`design_manifest.md`](design_manifest.md).
