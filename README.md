# RtedStart

Менеджер локальных сервисов с графическим интерфейсом. Удобен когда нужно держать запущенными несколько процессов одновременно — бекенд, фронтенд, тоннель, воркеры — и не плодить десяток терминалов.

A local service manager with a GUI. Handy when you need to keep multiple processes running at once — backend, frontend, tunnel, workers — without juggling a dozen terminals.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green)
![Windows](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## Возможности / Features

- **Вкладки / Tabs** — каждый сервис в своей вкладке с консольным выводом и ANSI-цветами / each service in its own tab with console output and ANSI colors
- **Home** — сводная таблица: статус, PID, аптайм, CPU, память / dashboard with status, PID, uptime, CPU, memory
- **Авто-перезагрузка / Auto-reload** — следит за файлами, перезапускает сервис. Исключения через glob-паттерны / watches files, restarts the service. Exclusions via glob patterns
- **Автозапуск / Auto-start** — отмеченные сервисы стартуют вместе с программой / selected services launch with the app
- **Управление / Controls** — Start / Stop / Restart по отдельности или все сразу / individually or all at once
- **Конфиг / Config** — `starter_config.json` рядом с программой, редактируется через GUI или руками / next to the app, editable via GUI or manually

## Запуск / Usage

```
python starter.py
```

Или через собранный exe (см. Сборка). При первом запуске конфига нет — пустое окно, жми `+` и добавляй сервисы.

Or via compiled exe (see Build). On first run there's no config — empty window, press `+` to add services.

### Аргументы / Arguments

```
python starter.py -c path/to/config.json
```

Если не указан — ищет `starter_config.json` рядом с собой.

If not specified — looks for `starter_config.json` next to itself.

## Конфиг / Config

```json
{
  "services": [
    {
      "name": "Backend",
      "command": "python -m uvicorn app.main:app --port 8000",
      "cwd": "C:/projects/myapp/backend",
      "auto_restart": true,
      "auto_start": false,
      "watch_dir": "",
      "watch_exclude": ["__pycache__", "*.pyc", "logs/*"]
    }
  ]
}
```

| Поле / Field | RU | EN |
|---|---|---|
| `name` | Название вкладки | Tab name |
| `command` | Команда запуска | Launch command |
| `cwd` | Рабочая директория | Working directory |
| `auto_restart` | Перезапуск при изменении файлов | Restart on file changes |
| `auto_start` | Запуск при старте программы | Launch on app start |
| `watch_dir` | Директория для отслеживания (пусто = `cwd`) | Watch directory (empty = `cwd`) |
| `watch_exclude` | Glob-паттерны исключений | Exclusion glob patterns |

## Зависимости / Dependencies

```
pip install PyQt6
pip install psutil  # optional — CPU & memory monitoring
```

Без psutil всё работает, просто в таблице Home вместо цифр будут прочерки.

Without psutil everything works, the Home table just shows dashes instead of numbers.

## Сборка / Build

```
pip install nuitka
python -m nuitka --onefile --enable-plugin=pyqt6 --windows-console-mode=disable --output-filename=RtedStart.exe starter.py
```

## Отслеживаемые расширения / Watched extensions

`.py` `.js` `.ts` `.tsx` `.jsx` `.json` `.html` `.css` `.toml` `.yaml` `.yml` `.cfg` `.ini` `.env` `.sql` `.rs` `.go` `.java` `.kt` `.rb` `.php` `.c` `.cpp` `.h`

Директории `__pycache__`, `.git`, `node_modules`, `.venv` пропускаются всегда.

Directories `__pycache__`, `.git`, `node_modules`, `.venv` are always skipped.

## Лицензия / License

MIT
