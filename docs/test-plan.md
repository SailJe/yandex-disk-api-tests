# Test plan

Цель: проверить основные операции REST API Яндекс.Диска на отдельном аккаунте
без зависимости между тестами и без изменения пользовательских данных.

## 24 интеграционных сценария

| № | Файл / сценарий | Метод и ожидание | Проверка состояния |
| --- | --- | --- | --- |
| 1 | resources: создание папки | PUT `201`, GET `200` | Имя, путь, тип, даты, пустой список |
| 2–4 | resources: Unicode / пробелы / спецсимволы | PUT `201`, GET `200` | Точное имя и путь, наличие в родительском каталоге |
| 5 | resources: пагинация | GET `200` | Три ресурса, sort/limit/offset/total, без пропусков и дублей |
| 6 | resources: fields | GET `200` | Только запрошенные name/path/type |
| 7 | resources: удаление пустой папки | DELETE `204` | GET `404`, идемпотентный teardown |
| 8 | resources: удаление непустой папки | DELETE `202` | Operation success, родитель и ребёнок отсутствуют |
| 9 | files: загрузка | GET upload `200`, PUT storage `201`/`202` | Metadata, размер, MD5, даты, MIME, скачанные байты |
| 10 | files: upload overwrite=true | GET upload `200`, PUT storage `201`/`202` | Новый размер/MD5 и новые байты |
| 11 | files: копирование файла | POST copy `201` | Source и destination содержат исходные данные |
| 12 | files: перемещение файла | POST move `202` | Operation success, destination цел, source отсутствует |
| 13 | files: копирование непустой папки | POST copy `202` | Operation success, дочерний файл и исходная папка целы |
| 14 | negative: отсутствующий ресурс | GET `404` | Структура Error |
| 15 | negative: удаление отсутствующего ресурса | DELETE `404` | GET подтверждает отсутствие |
| 16 | negative: пропущен обязательный path | PUT `400` | Структура Error |
| 17 | negative: отсутствующий source для copy | POST `404` | Source и destination отсутствуют |
| 18 | negative: upload overwrite=false | GET upload `409` | Metadata и байты оригинала не изменились |
| 19–20 | negative: copy / move overwrite=false | POST `409` | Metadata и разные исходные байты обоих файлов сохранены |
| 21 | auth: валидный токен | GET `200` | path/type корня |
| 22–23 | auth: нет токена / неверный токен | GET `401` | Структура Error |
| 24 | e2e: create → upload → copy → move → download → delete | GET/PUT/POST/DELETE | Контроль переходов состояния, в конце каталог пуст |

Для перемещения в позитивных сценариях и операций над непустыми каталогами
явно задан `force_async=true`. После статуса операции `success` проверяется
состояние ресурсов через GET. Копирование файла и удаление пустой папки
проверяются в синхронном режиме. Cleanup принимает
`204`/`202`, поскольку удаляемый корень может быть пустым или непустым, и `404`,
если он уже удалён тестом.

## Проверенные официальные контракты

| Контракт | Источник |
| --- | --- |
| OAuth, host, пути, права приложения | [Доступ к API](https://yandex.ru/dev/disk-api/doc/ru/concepts/quickstart) |
| PUT create `201`, path обязателен, `400` | [Создание папки](https://yandex.ru/dev/disk-api/doc/ru/reference/create-folder) |
| GET metadata `200`, `401`, `404`, fields, pagination | [Метаинформация](https://yandex.ru/dev/disk-api/doc/ru/reference/meta) |
| GET upload `200`/`409`, overwrite, PUT `201`/`202` | [Загрузка](https://yandex.ru/dev/disk-api/doc/ru/reference/upload) |
| GET download link `200`, скачивание `200`/`302` | [Скачивание](https://yandex.ru/dev/disk-api/doc/ru/reference/content) |
| POST copy `201`/`202`, `404`, `409`, overwrite | [Копирование](https://yandex.ru/dev/disk-api/doc/ru/reference/copy) |
| POST move `201`/`202`, `409`, overwrite | [Перемещение](https://yandex.ru/dev/disk-api/doc/ru/reference/move) |
| DELETE `204`/`202`, `404`, permanently | [Удаление](https://yandex.ru/dev/disk-api/doc/ru/reference/delete) |
| GET operation `200`, success/failed/in-progress | [Статус операции](https://yandex.ru/dev/disk-api/doc/ru/reference/operations) |
| Resource, ResourceList, Link, Error | [JSON-объекты](https://yandex.ru/dev/disk-api/doc/ru/reference/response-objects) |

Проверены актуальные страницы документации и их официальные `.md`-версии
18.09.2026. На странице создания папки список ошибок неполный: `409` там не
указан. Поэтому проверка конфликтов привязана к upload/copy/move, где этот код
описан явно. Идентификаторы конкретных ошибок не угадываются: проверяется
HTTP-код и наличие непустых строк `error`, `message`, `description`.

## 14 offline-проверок инфраструктуры

Отдельно моделируются кодирование параметров, таймауты запросов, отсутствие
OAuth у storage-запросов, проверка адреса operation, ожидание успешной операции,
ошибка операции, исчерпание deadline, устаревшая metadata при overwrite,
немедленный отказ при `401`, безопасное сообщение транспортной ошибки,
cleanup после ошибки setup, cleanup после падения теста с асинхронным DELETE,
повторный cleanup уже удалённого каталога. Смежные проверки объединены в тесты;
сеть и часы подменены средствами pytest и стандартной библиотеки.

Отдельно проверяются ожидание исчезновения ресурса (`200` → `404`) и ошибка
по таймауту, если ресурс остался на месте. Ошибка содержит путь и последний
HTTP-статус.

Эти проверки подтверждают поведение тестовой инфраструктуры. Они не заменяют
24 интеграционных сценария и не служат доказательством выполнения API-контракта.
