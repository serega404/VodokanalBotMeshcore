import os

from src.cyr2lat import cyr2lat


MESHCORE_MESSAGE_LIMIT_BYTES_ENV = 'MESHCORE_MESSAGE_LIMIT_BYTES'
MESHCORE_CYR2LAT_MODE_ENV = 'MESHCORE_CYR2LAT_MODE'
MESHCORE_CHUNK_DELAY_MS_ENV = 'MESHCORE_CHUNK_DELAY_MS'
MESHCORE_POST_DELAY_MS_ENV = 'MESHCORE_POST_DELAY_MS'
DEFAULT_MESHCORE_MESSAGE_LIMIT_BYTES = 133
DEFAULT_MESHCORE_CYR2LAT_MODE = 'soft'
DEFAULT_MESHCORE_CHUNK_DELAY_MS = 0
DEFAULT_MESHCORE_POST_DELAY_MS = 1000
MIN_MESHCORE_MESSAGE_LIMIT_BYTES = 50


def byte_length(text):
    return len(text.encode("utf-8"))


def parse_meshcore_message_limit():
    raw_limit = os.environ.get(
        MESHCORE_MESSAGE_LIMIT_BYTES_ENV,
        str(DEFAULT_MESHCORE_MESSAGE_LIMIT_BYTES),
    )
    try:
        limit = int(raw_limit)
    except ValueError:
        raise ValueError(MESHCORE_MESSAGE_LIMIT_BYTES_ENV + " must be an integer")

    if limit < MIN_MESHCORE_MESSAGE_LIMIT_BYTES:
        raise ValueError(
            MESHCORE_MESSAGE_LIMIT_BYTES_ENV
            + " must be at least "
            + str(MIN_MESHCORE_MESSAGE_LIMIT_BYTES)
            + " bytes"
        )

    return limit


def parse_meshcore_cyr2lat_mode():
    mode = os.environ.get(MESHCORE_CYR2LAT_MODE_ENV, DEFAULT_MESHCORE_CYR2LAT_MODE)
    if mode not in ('full', 'off', 'soft'):
        raise ValueError(MESHCORE_CYR2LAT_MODE_ENV + " must be 'full', 'off' or 'soft'")

    return mode


def parse_meshcore_chunk_delay_ms():
    raw_delay = os.environ.get(
        MESHCORE_CHUNK_DELAY_MS_ENV,
        str(DEFAULT_MESHCORE_CHUNK_DELAY_MS),
    )
    try:
        delay = int(raw_delay)
    except ValueError:
        raise ValueError(MESHCORE_CHUNK_DELAY_MS_ENV + " must be an integer")

    if delay < 0:
        raise ValueError(MESHCORE_CHUNK_DELAY_MS_ENV + " must be zero or greater")

    return delay


def parse_meshcore_post_delay_ms():
    raw_delay = os.environ.get(
        MESHCORE_POST_DELAY_MS_ENV,
        str(DEFAULT_MESHCORE_POST_DELAY_MS),
    )
    try:
        delay = int(raw_delay)
    except ValueError:
        raise ValueError(MESHCORE_POST_DELAY_MS_ENV + " must be an integer")

    if delay < 0:
        raise ValueError(MESHCORE_POST_DELAY_MS_ENV + " must be zero or greater")

    return delay


def split_long_word(word, limit):
    chunks = []
    chunk = ''

    for char in word:
        if byte_length(char) > limit:
            raise ValueError("Single character does not fit MeshCore message limit")

        candidate = chunk + char
        if byte_length(candidate) <= limit:
            chunk = candidate
            continue

        chunks.append(chunk)
        chunk = char

    if chunk:
        chunks.append(chunk)

    return chunks


def split_text_by_byte_limit(message, limit):
    words = message.split()
    if not words:
        return [message] if byte_length(message) <= limit else split_long_word(message, limit)

    chunks = []
    chunk = ''

    for word in words:
        if byte_length(word) > limit:
            if chunk:
                chunks.append(chunk)
                chunk = ''
            chunks.extend(split_long_word(word, limit))
            continue

        candidate = word if not chunk else chunk + ' ' + word
        if byte_length(candidate) <= limit:
            chunk = candidate
            continue

        chunks.append(chunk)
        chunk = word

    if chunk:
        chunks.append(chunk)

    return chunks


def max_chunk_prefix_length(total_digits):
    max_number = '9' * total_digits
    return byte_length("[" + max_number + "/" + max_number + "] ")


def split_meshcore_message(message, limit):
    if byte_length(message) <= limit:
        return [message]

    total_digits = 1
    while True:
        prefix_length = max_chunk_prefix_length(total_digits)
        if prefix_length >= limit:
            raise ValueError("MeshCore message limit is too small for chunk prefixes")

        chunks = split_text_by_byte_limit(message, limit - prefix_length)
        next_total_digits = len(str(len(chunks)))
        if next_total_digits == total_digits:
            total = len(chunks)
            return [
                "[" + str(index) + "/" + str(total) + "] " + chunk
                for index, chunk in enumerate(chunks, start=1)
            ]

        total_digits = next_total_digits


def prepare_meshcore_messages(message, limit, cyr2lat_mode=DEFAULT_MESHCORE_CYR2LAT_MODE):
    return split_meshcore_message(cyr2lat(message, mode=cyr2lat_mode), limit)
