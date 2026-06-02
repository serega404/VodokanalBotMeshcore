import asyncio
import os

from src.meshcore_common import (
    DEFAULT_MESHCORE_CHUNK_DELAY_MS,
    DEFAULT_MESHCORE_CYR2LAT_MODE,
    DEFAULT_MESHCORE_MESSAGE_LIMIT_BYTES,
    parse_meshcore_chunk_delay_ms,
    parse_meshcore_cyr2lat_mode,
    parse_meshcore_message_limit,
    parse_meshcore_post_delay_ms,
    prepare_meshcore_messages,
)
from src.parser import (
    DEFAULT_DB_PATH,
    DEFAULT_VODOKANAL_URL,
    create_session,
    fetch_posts,
    get_new_posts,
    load_database,
    save_database,
)


PROXY_URL = os.environ.get('PROXY_URL', '')
MESHCORE_TCP_HOST_ENV = 'MESHCORE_TCP_HOST'
MESHCORE_TCP_PORT_ENV = 'MESHCORE_TCP_PORT'
MESHCORE_TCP_TIMEOUT_SECONDS_ENV = 'MESHCORE_TCP_TIMEOUT_SECONDS'
MESHCORE_CHANNEL_ENV = 'MESHCORE_CHANNEL'
DEFAULT_MESHCORE_TCP_PORT = 5000
DEFAULT_MESHCORE_TCP_TIMEOUT_SECONDS = 15.0
DEFAULT_MESHCORE_CHANNEL = 5
MESHCORE_TCP_INBOUND_FRAME_MARKERS = (b"\x3e", b"\x3c")


def parse_meshcore_tcp_host():
    host = os.environ.get(MESHCORE_TCP_HOST_ENV, '').strip()
    if host == '':
        raise ValueError(MESHCORE_TCP_HOST_ENV + " is not set")

    return host


def parse_meshcore_tcp_port():
    raw_port = os.environ.get(
        MESHCORE_TCP_PORT_ENV,
        str(DEFAULT_MESHCORE_TCP_PORT),
    )
    try:
        port = int(raw_port)
    except ValueError:
        raise ValueError(MESHCORE_TCP_PORT_ENV + " must be an integer")

    if port <= 0 or port > 65535:
        raise ValueError(MESHCORE_TCP_PORT_ENV + " must be between 1 and 65535")

    return port


def parse_meshcore_tcp_timeout_seconds():
    raw_timeout = os.environ.get(
        MESHCORE_TCP_TIMEOUT_SECONDS_ENV,
        str(DEFAULT_MESHCORE_TCP_TIMEOUT_SECONDS),
    )
    try:
        timeout = float(raw_timeout)
    except ValueError:
        raise ValueError(MESHCORE_TCP_TIMEOUT_SECONDS_ENV + " must be a number")

    if timeout <= 0:
        raise ValueError(MESHCORE_TCP_TIMEOUT_SECONDS_ENV + " must be greater than 0")

    return timeout


def parse_meshcore_channel():
    raw_channel = os.environ.get(
        MESHCORE_CHANNEL_ENV,
        str(DEFAULT_MESHCORE_CHANNEL),
    )
    try:
        channel = int(raw_channel)
    except ValueError:
        raise ValueError(MESHCORE_CHANNEL_ENV + " must be an integer")

    if channel < 0:
        raise ValueError(MESHCORE_CHANNEL_ENV + " must be zero or greater")

    return channel


async def create_meshcore_tcp_connection(
    host,
    port,
    meshcore_class=None,
    timeout=DEFAULT_MESHCORE_TCP_TIMEOUT_SECONDS,
):
    if meshcore_class is None:
        from meshcore import EventType, MeshCore

        meshcore = await create_default_meshcore_tcp_connection(
            MeshCore,
            host,
            port,
            timeout,
        )
        error_event_type = EventType.ERROR
    else:
        error_event_type = getattr(meshcore_class, 'ERROR_EVENT_TYPE', None)
        meshcore = await meshcore_class.create_tcp(
            host,
            port,
            default_timeout=timeout,
        )

    if meshcore is None:
        raise ConnectionError(
            "No response from MeshCore TCP node after "
            + str(timeout)
            + " seconds. Check "
            + MESHCORE_TCP_HOST_ENV
            + ", "
            + MESHCORE_TCP_PORT_ENV
            + ", and that TCP companion access is enabled."
        )

    return meshcore, error_event_type


async def create_default_meshcore_tcp_connection(meshcore_class, host, port, timeout):
    from meshcore import TCPConnection

    class CompatibleTCPConnection(TCPConnection):
        def handle_rx(self, data):
            if len(self.header) == 0:
                idx = find_first_meshcore_frame_marker(data)
                if idx < 0:
                    return
                data = data[idx:]
                self.header = data[0:1]
                data = data[1:]

            if len(self.header) < 3:
                while len(self.header) < 3 and len(data) > 0:
                    self.header = self.header + data[0:1]
                    data = data[1:]
                if len(self.header) < 3:
                    return

                self.frame_expected_size = int.from_bytes(
                    self.header[1:],
                    "little",
                    signed=False,
                )
                if self.frame_expected_size > 300:
                    self.header = b""
                    self.inframe = b""
                    self.frame_expected_size = 0
                    if len(data) > 0:
                        self.handle_rx(data)
                    return

            upbound = self.frame_expected_size - len(self.inframe)
            if len(data) < upbound:
                self.inframe = self.inframe + data
                return

            self.inframe = self.inframe + data[0:upbound]
            data = data[upbound:]
            self._receive_count += 1
            if self.reader is not None:
                self._spawn_background(self.reader.handle_rx(self.inframe))

            self.inframe = b""
            self.header = b""
            self.frame_expected_size = 0
            if len(data) > 0:
                self.handle_rx(data)

    connection = CompatibleTCPConnection(host, port)
    meshcore = meshcore_class(connection, default_timeout=timeout)
    result = await meshcore.connect()
    if result is None:
        await meshcore.disconnect()
        return None

    return meshcore


def find_first_meshcore_frame_marker(data):
    found_indexes = [
        index
        for index in (data.find(marker) for marker in MESHCORE_TCP_INBOUND_FRAME_MARKERS)
        if index >= 0
    ]
    if not found_indexes:
        return -1

    return min(found_indexes)


def raise_for_meshcore_error(result, error_event_type, action):
    if error_event_type is not None and result.type == error_event_type:
        raise RuntimeError("MeshCore " + action + " error: " + str(result.payload))


async def send_meshcore_tcp_message(
    meshcore,
    error_event_type,
    channel,
    message,
    limit=DEFAULT_MESHCORE_MESSAGE_LIMIT_BYTES,
    cyr2lat_mode=DEFAULT_MESHCORE_CYR2LAT_MODE,
    chunk_delay_ms=DEFAULT_MESHCORE_CHUNK_DELAY_MS,
):
    parts = prepare_meshcore_messages(message, limit, cyr2lat_mode)
    for index, part in enumerate(parts):
        print(
            "MeshCore TCP chunk "
            + str(index + 1)
            + "/"
            + str(len(parts))
            + " to channel "
            + str(channel)
            + ": "
            + part
        )
        result = await meshcore.commands.send_chan_msg(channel, part)
        raise_for_meshcore_error(result, error_event_type, "send channel message")
        if chunk_delay_ms > 0 and index < len(parts) - 1:
            await asyncio.sleep(chunk_delay_ms / 1000)


async def publish_new_posts_async(send_message, session, db_path=DEFAULT_DB_PATH):
    database = load_database(db_path)
    posts = fetch_posts(session, DEFAULT_VODOKANAL_URL)

    if not posts:
        print("No posts")
        return

    print("The number of posts for this day:", len(posts))

    new_posts = get_new_posts(posts, database)
    if not new_posts:
        print("No new posts")
        return

    for post in new_posts:
        await send_message(post.text)

    save_database(posts, db_path)


async def main_async():
    try:
        host = parse_meshcore_tcp_host()
        port = parse_meshcore_tcp_port()
        tcp_timeout_seconds = parse_meshcore_tcp_timeout_seconds()
        channel = parse_meshcore_channel()
        message_limit = parse_meshcore_message_limit()
        cyr2lat_mode = parse_meshcore_cyr2lat_mode()
        chunk_delay_ms = parse_meshcore_chunk_delay_ms()
        post_delay_ms = parse_meshcore_post_delay_ms()
    except ValueError as error:
        print(error)
        return

    session = create_session(PROXY_URL)
    meshcore = None
    try:
        meshcore, error_event_type = await create_meshcore_tcp_connection(
            host,
            port,
            timeout=tcp_timeout_seconds,
        )

        first_message = True

        async def send_message(message):
            nonlocal first_message

            if first_message:
                first_message = False
            elif post_delay_ms > 0:
                await asyncio.sleep(post_delay_ms / 1000)

            await send_meshcore_tcp_message(
                meshcore,
                error_event_type,
                channel,
                message,
                message_limit,
                cyr2lat_mode,
                chunk_delay_ms,
            )

        await publish_new_posts_async(send_message, session)
    except (RuntimeError, ValueError, ConnectionError) as error:
        print(error)
    finally:
        if meshcore is not None:
            await meshcore.disconnect()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
