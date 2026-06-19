# RtedStart

**RtedStart** — менеджер локальных сервисов с графическим интерфейсом на PyQt6.

Устал держать кучу отдельных окон терминала для каждого сервиса? RtedStart собирает всё в одном месте — запускай, останавливай и перезапускай процессы в пару кликов.

## Features

- **Вкладки с живой консолью** — каждый сервис в своей вкладке, вывод в реальном времени с поддержкой ANSI-цветов
- - **Вкладка Home** — общая таблица всех сервисов: статус, PID, аптайм, CPU и потребление памяти
  - - **Авто-перезагрузка** — следит за изменениями файлов и перезапускает сервис, с настраиваемыми исключениями по glob-паттернам
    - - **Автозапуск** — выбранные сервисы стартуют автоматически при открытии приложения
      - - **Мониторинг ресурсов** — CPU и RAM через `psutil` (опционально)
        - - **JSON-конфиг** — простой файл конфигурации рядом с программой
          - - **Standalone exe** — собирается в один исполняемый файл через Nuitka
           
            - ## Requirements
           
            - - Python 3.10+
              - - PyQt6
                - - psutil *(optional, for resource monitoring)*
                 
                  - ## Installation
                 
                  - ```bash
                    git clone https://github.com/RtedDima/RtedStart.git
                    cd RtedStart
                    pip install -r requirements.txt
                    python main.py
                    ```

                    ## Build (standalone exe)

                    ```bash
                    nuitka --standalone --onefile --plugin-enable=pyqt6 main.py
                    ```

                    ## Configuration

                    Конфигурация хранится в `config.json` рядом с исполняемым файлом. Пример:

                    ```json
                    {
                      "services": [
                        {
                          "name": "Backend",
                          "command": "python server.py",
                          "cwd": "./backend",
                          "autostart": true,
                          "watch": true,
                          "watch_exclude": ["*.pyc", "__pycache__/**"]
                        }
                      ]
                    }
                    ```

                    ## License

                    MIT
