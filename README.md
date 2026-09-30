# blame-likumi-lv

`blame-likumi-lv` строит обычную Git-историю официальных редакций законов с
[Likumi.lv](https://likumi.lv). В MVP поддерживаются документы типа `likums`.
Исходные HTML-файлы хранятся только в локальном, игнорируемом `cache/`.

## Быстрый старт

Нужны Python 3.11+ и Git.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
blame-likumi fetch
blame-likumi build
blame-likumi verify
```

Полный pipeline:

```powershell
blame-likumi generate
```

По умолчанию второй репозиторий создаётся в `../latvian-laws`. Его можно
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

## Ограничения MVP

Для окончательного acceptance test необходимо выполнить `generate` с доступом
к Likumi.lv и получить `5/5 VERIFIED`. В репозитории генератора намеренно нет
скачанных текстов и сгенерированного набора законов.

