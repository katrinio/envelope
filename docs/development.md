# Разработка

Проект — небольшое приложение на FastAPI с серверными HTML-шаблонами. Для базы используется SQLAlchemy, а изменения схемы проходят через Alembic.

## Быстрый старт

Нужны Python 3.14 и Poetry.

```bash
poetry install
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload
```

После запуска страница пользователя доступна по адресу:

```text
http://127.0.0.1:8000/users/1/envelopes/page
```

Пользователь с таким `id` должен уже существовать в базе. Для локальной проверки можно добавить пользователя и первый конверт одной командой:

```bash
poetry run python -c 'from src.orm.user import User; from src.orm.envelope import Envelope; user = User.get(1) or User.create(userId=1, username="alice", salary=100000); Envelope.for_user(user.id) or [Envelope.create(user_id=user.id, name="Emergency fund", current_amount=25000, target_amount=100000, priority=1)]'
```

## Где что лежит

- `src/orm/` — модели пользователя и конверта.
- `src/envelope/routes/` — JSON API и HTML-маршруты.
- `src/template/` — Jinja-шаблоны.
- `src/static/` — стили интерфейса.
- `migrations/` — история изменений базы.
- `tests/` — проверки API, страницы и Active Record.

В проекте используется простой Active Record-подход: модели умеют создавать, читать, сохранять и удалять свои записи.

## Проверки

Перед коммитом достаточно выполнить:

```bash
poetry run pytest
poetry run ruff check .
poetry run mypy src
```

Новые изменения лучше держать небольшими. Визуальные решения стоит сверять с [`design_manifest.md`](design_manifest.md).
