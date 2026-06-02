# VodokanalParser

[![MIT License](https://img.shields.io/github/license/serega404/VodokanalBot)](https://github.com/serega404/VodokanalBot)

## Запуск с MeshCore + Home Assistant

Вариант для MeshCore отправляет новые сообщения в webhook Home Assistant, а Home Assistant пересылает их в канал MeshCore.

1. Добавь в Home Assistant автоматизацию [`Webhook to MeshCore channel`](https://github.com/serega404/HA-MeshCore#webhook-to-meshcore-channel).
2. Замени `CHANGE_ME_RANDOM_WEBHOOK_ID` в автоматизации на случайную строку.

``` Docker
docker volume create vodokanal_bot_data
docker run -d --name VodokanalBot \
    --restart=always \
    -v vodokanal_bot_data:/app/data \
    -e TZ='Europe/Moscow' \
    -e HOME_ASSISTANT_WEBHOOK_ID='CHANGE_ME_RANDOM_WEBHOOK_ID' \
    -e HOME_ASSISTANT_URL='http://homeassistant.local:8123' \
    -e HOME_ASSISTANT_WEBHOOK_CHANNEL='0' \
    -e MESHCORE_MESSAGE_LIMIT_BYTES='133' \
    -e MESHCORE_CYR2LAT_MODE='soft' \
    -e MESHCORE_CHUNK_DELAY_MS='0' \
    -e MESHCORE_POST_DELAY_MS='1000' \
    ghcr.io/serega404/vodokanalbotmeshcore/vodokanalbot-meshcore-ha:main
```

Перед отправкой в MeshCore текст транслитерируется и делится на части по `MESHCORE_MESSAGE_LIMIT_BYTES` байт. По умолчанию используется лимит `133` и мягкий режим `MESHCORE_CYR2LAT_MODE=soft`, где заменяются только похожие буквы. Для полной транслитерации укажи `MESHCORE_CYR2LAT_MODE=full`, для отключения транслитерации — `MESHCORE_CYR2LAT_MODE=off`. Задержку между частями одного длинного сообщения можно задать через `MESHCORE_CHUNK_DELAY_MS` в миллисекундах, по умолчанию `0`. Задержка между несколькими новыми постами задаётся через `MESHCORE_POST_DELAY_MS`, по умолчанию `1000`.

### Запуск в Docker Compose

Укажи `HOME_ASSISTANT_WEBHOOK_ID` и `HOME_ASSISTANT_WEBHOOK_CHANNEL` в [`docker-compose.ha.yml`](./docker-compose.ha.yml), затем запусти:

``` Docker
docker compose -f docker-compose.ha.yml up -d --build
```

## Запуск с MeshCore напрямую по TCP

Этот вариант подключается к MeshCore companion node по TCP через Python-библиотеку `meshcore` и отправляет сообщения в канал через `send_chan_msg`.

``` Docker
docker volume create vodokanal_bot_data
docker run -d --name VodokanalBot \
    --restart=always \
    -v vodokanal_bot_data:/app/data \
    -e TZ='Europe/Moscow' \
    -e MESHCORE_TCP_HOST='192.168.1.100' \
    -e MESHCORE_TCP_PORT='5000' \
    -e MESHCORE_TCP_TIMEOUT_SECONDS='15' \
    -e MESHCORE_CHANNEL='5' \
    -e MESHCORE_MESSAGE_LIMIT_BYTES='133' \
    -e MESHCORE_CYR2LAT_MODE='soft' \
    -e MESHCORE_CHUNK_DELAY_MS='0' \
    -e MESHCORE_POST_DELAY_MS='1000' \
    ghcr.io/serega404/vodokanalbotmeshcore/vodokanalbot-meshcore:main
```

Перед запуском включи TCP-доступ на MeshCore companion node и укажи его IP в `MESHCORE_TCP_HOST`. Порт по умолчанию — `5000`, таймаут ответа — `15` секунд, канал по умолчанию — `5`.

### Запуск в Docker Compose

Укажи `MESHCORE_TCP_HOST` и `MESHCORE_CHANNEL` в [`docker-compose.meshcore.yml`](./docker-compose.meshcore.yml), затем запусти:

``` Docker
docker compose -f docker-compose.meshcore.yml up -d --build
```

## Интеграции

Общая логика парсинга, работы с `data/db.json` и поиска новых сообщений вынесена в [`src/parser.py`](./src/parser.py).

Для новой интеграции достаточно создать свой адаптер отправки и передать его в `publish_new_posts`:

``` Python
from src.parser import create_session, publish_new_posts

session = create_session()

publish_new_posts(
    send_message=lambda message: print(message),
    session=session,
    url="http://www.tgnvoda.ru/avarii.php",
)
```

## Библиотеки

* [Requests](https://requests.readthedocs.io/en/latest/)
* [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
* [meshcore](https://github.com/meshcore-dev/meshcore_py)

## Лицензия

Распространяется под MIT License. Смотри файл [`LICENSE`](./LICENSE) для того что бы узнать подробности.
