# API-тесты Яндекс.Диска

## Что тестируется

GET, PUT, POST и DELETE: создание и удаление папок, загрузка и перезапись файлов,
копирование и перемещение, авторизация, ошибки и конфликты. Есть проверки
Unicode, пробелов и спецсимволов в именах, сохранности данных после ошибки и E2E.

Всего 24 API-сценария и 14 тестов клиента и cleanup без обращения к сети.
Подробности — в [тест-плане](docs/test-plan.md). Контракты взяты из
[документации Яндекс.Диска](https://yandex.ru/dev/disk-api/doc/ru/).

## Стек

Python 3.11+, pytest, requests, python-dotenv. Для проверки кода — Ruff.

## Установка

```bash
git clone https://github.com/SailJe/yandex-disk-api-tests.git
cd yandex-disk-api-tests
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

В Windows окружение активируется командой `.venv\Scripts\Activate.ps1`.

## Токен

Нужен OAuth-токен отдельного тестового аккаунта с правами
`cloud_api:disk.read` и `cloud_api:disk.write`. Личный аккаунт не используйте.

Скопируйте `.env.example` в `.env` и замените значение своим токеном:

```dotenv
YANDEX_DISK_TOKEN=your_token_here
```

Можно задать `YANDEX_DISK_TOKEN` через переменную окружения — она имеет приоритет
над `.env`. Файл `.env` исключён из Git. Без токена API-тесты пропускаются.

## Запуск

Из корня проекта с активированным окружением:

```bash
pytest -v
pytest -m smoke
pytest -m negative
pytest -m unit
```

`smoke` — основные операции, `negative` — ошибки, `unit` — тесты без сети.
Также доступны `auth`, `e2e` и `integration`.

## Структура

```text
src/api/disk_client.py
tests/
  conftest.py
  helpers.py
  test_resources.py
  test_files.py
  test_auth.py
  test_negative.py
  test_e2e.py
  unit/test_client.py
docs/test-plan.md
.github/workflows/tests.yml
pyproject.toml
pytest.ini
```

## Основные решения

- HTTP-запросы вынесены в `DiskClient` на основе `requests.Session`, общие проверки — в `helpers.py`.
- Каждый тест, создающий ресурсы, получает свою UUID-папку. Имена дочерних ресурсов тоже содержат UUID.
- Fixtures с `yield` и `finally` удаляют папку вместе с содержимым даже при падении теста. Повторное удаление допускается.
- После изменений проверяется состояние через GET. У файлов проверяются metadata, размер, MD5 и скачанное содержимое.
- Асинхронные операции ожидаются с опросом статуса и таймаутом. Загрузка и скачивание используют отдельную сессию без OAuth.

## CI

На push и pull request GitHub Actions запускает Ruff и тесты без сети
на Python 3.11 и 3.14.

Для API-тестов добавьте GitHub Secret `YANDEX_DISK_TOKEN` в настройках репозитория
и запустите **Actions → API tests → Run workflow**. Без секрета API-job завершится
ошибкой. Одновременно выполняется только один API-прогон.

## Ограничения

- Тесты обращаются к реальному API. Нужны сеть, доступный сервис и свободное место на тестовом Диске.
- Нагрузочное тестирование, публичные ссылки и корзина не покрыты.
- При аварийной остановке процесса или недоступности API могут остаться папки `qa-api-…`; их нужно удалить вручную.
- Автоматическое использование proxy из переменных окружения отключено. При необходимости proxy задаётся в клиенте.
