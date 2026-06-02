import os
import time

from src.meshcore_common import (
    DEFAULT_MESHCORE_CHUNK_DELAY_MS,
    DEFAULT_MESHCORE_CYR2LAT_MODE,
    parse_meshcore_chunk_delay_ms,
    parse_meshcore_cyr2lat_mode,
    parse_meshcore_message_limit,
    parse_meshcore_post_delay_ms,
    prepare_meshcore_messages,
)
from src.parser import create_session, publish_new_posts


PROXY_URL = os.environ.get('PROXY_URL', '')
HOME_ASSISTANT_URL = os.environ.get('HOME_ASSISTANT_URL', '')
HOME_ASSISTANT_WEBHOOK_ID = os.environ.get('HOME_ASSISTANT_WEBHOOK_ID', '')
HOME_ASSISTANT_WEBHOOK_CHANNEL = os.environ.get('HOME_ASSISTANT_WEBHOOK_CHANNEL', '0')


def create_webhook_url():
    return (
        HOME_ASSISTANT_URL.rstrip('/')
        + "/api/webhook/"
        + HOME_ASSISTANT_WEBHOOK_ID
    )


def send_webhook_message(session, message):
    req = session.get(
        create_webhook_url(),
        params={
            'channel': HOME_ASSISTANT_WEBHOOK_CHANNEL,
            'message': message,
        },
    )
    if not 200 <= req.status_code < 300:
        print("Home Assistant webhook request error: " + str(req.status_code))
        exit()
    else:
        print("Home Assistant webhook message sent")


def send_meshcore_message(
    session,
    message,
    limit,
    cyr2lat_mode=DEFAULT_MESHCORE_CYR2LAT_MODE,
    chunk_delay_ms=DEFAULT_MESHCORE_CHUNK_DELAY_MS,
):
    parts = prepare_meshcore_messages(message, limit, cyr2lat_mode)
    for index, part in enumerate(parts):
        print(
            "MeshCore chunk "
            + str(index + 1)
            + "/"
            + str(len(parts))
            + ": "
            + part
        )
        send_webhook_message(session, part)
        if chunk_delay_ms > 0 and index < len(parts) - 1:
            time.sleep(chunk_delay_ms / 1000)


def create_delayed_send_message(send_message, post_delay_ms):
    first_message = True

    def delayed_send_message(message):
        nonlocal first_message

        if first_message:
            first_message = False
        elif post_delay_ms > 0:
            time.sleep(post_delay_ms / 1000)

        send_message(message)

    return delayed_send_message


def main():
    if HOME_ASSISTANT_URL == '':
        print("Home Assistant URL is not set")
        exit()

    if HOME_ASSISTANT_WEBHOOK_ID == '':
        print("Home Assistant webhook id is not set")
        exit()

    try:
        message_limit = parse_meshcore_message_limit()
        cyr2lat_mode = parse_meshcore_cyr2lat_mode()
        chunk_delay_ms = parse_meshcore_chunk_delay_ms()
        post_delay_ms = parse_meshcore_post_delay_ms()
    except ValueError as error:
        print(error)
        exit()

    session = create_session(PROXY_URL)
    try:
        publish_new_posts(
            send_message=create_delayed_send_message(
                lambda message: send_meshcore_message(
                    session,
                    message,
                    message_limit,
                    cyr2lat_mode,
                    chunk_delay_ms,
                ),
                post_delay_ms,
            ),
            session=session,
        )
    except (RuntimeError, ValueError) as error:
        print(error)
        exit()


if __name__ == "__main__":
    main()
