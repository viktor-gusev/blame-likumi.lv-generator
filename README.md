# blame-likumi-lv

`blame-likumi-lv` строит обычную Git-историю официальных редакций законов и
постановлений с [Likumi.lv](https://likumi.lv). Каталог активных документов
включает законы Saeima и Ministru kabineta noteikumi; отдельные акты о
внесении изменений исключаются официальным фильтром каталога. Исходные
HTML-файлы хранятся только в локальном, игнорируемом `cache/`.

## Быстрый старт

Нужны Python 3.11+ и Git.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
blame-likumi catalog
blame-likumi fetch --workers 4
blame-likumi build
blame-likumi verify --workers 4
```

Полный pipeline:

```powershell
blame-likumi generate
```

По умолчанию используется `config/active-documents.json`, созданный командой
`catalog`. Второй репозиторий создаётся в `../latvian-laws`. Его можно
переопределить параметром `--output`. Для разработки одного parser:

```powershell
blame-likumi generate --law 45467 --output ../latvian-laws-one
```

Повторный запуск с тем же кэшем не скачивает уже сохранённые страницы.
Неизвестная структура страницы, отсутствие текста закона или несовпадение
verification завершают pipeline с ошибкой; данные молча не пропускаются.

## Архитектура

- `html_parser.py` извлекает официальный `.doc-body`, паспорт и даты редакций.
- `normalize.py` задаёт общую техническую нормализацию для build и verify.
- `fetcher.py` реализует локальный cache, rate limit, retry и backoff.
- `git_history.py` группирует snapshots по дате вступления в силу и создаёт
  исторические commits.
- `verification.py` сравнивает HEAD с актуальной редакцией Likumi.lv.

Генерируемые `.txt` содержат только нормализованный официальный текст закона.
Provenance находится в `metadata/*.json` и commit message.

## Каталог и cache

`catalog` получает активные документы через официальный публичный endpoint
Likumi.lv и сохраняет детерминированную конфигурацию. `cache/` ускоряет
повторный запуск и позволяет продолжить прерванную загрузку. Для полного
обновления каталога можно использовать `--refresh`.

`--workers 4` запускает четыре независимых документных worker-а, каждый со
своим rate limit. Для особенно бережной загрузки оставьте значение по
умолчанию `1`.

Скачанные тексты и сгенерированный набор законов намеренно не коммитятся в
репозиторий генератора.
