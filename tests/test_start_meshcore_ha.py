import asyncio
import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.cyr2lat import cyr2lat
from src.meshcore_common import (
    parse_meshcore_cyr2lat_mode,
    parse_meshcore_chunk_delay_ms,
    parse_meshcore_message_limit,
    parse_meshcore_post_delay_ms,
    prepare_meshcore_messages,
)
from start_meshcore_ha import (
    create_delayed_send_message,
    send_meshcore_message,
)
from start_meshcore_tcp import (
    create_meshcore_tcp_connection,
    find_first_meshcore_frame_marker,
    parse_meshcore_channel,
    parse_meshcore_tcp_host,
    parse_meshcore_tcp_port,
    parse_meshcore_tcp_timeout_seconds,
    raise_for_meshcore_error,
    send_meshcore_tcp_message,
)


class FakeResponse:
    status_code = 200


class FakeSession:
    def __init__(self):
        self.messages = []

    def get(self, url, params):
        self.messages.append(params['message'])
        return FakeResponse()


class FakeMeshCoreCommands:
    def __init__(self):
        self.messages = []

    async def send_chan_msg(self, channel, message):
        self.messages.append((channel, message))
        return SimpleNamespace(type='ok', payload={})


class FakeMeshCore:
    ERROR_EVENT_TYPE = 'error'

    def __init__(self):
        self.commands = FakeMeshCoreCommands()

    @classmethod
    async def create_tcp(cls, host, port, default_timeout=15.0):
        cls.host = host
        cls.port = port
        cls.default_timeout = default_timeout
        return cls()

    async def disconnect(self):
        self.disconnected = True


class FakeMeshCoreNoResponse:
    @classmethod
    async def create_tcp(cls, host, port, default_timeout=15.0):
        return None


def asyncio_run(coro):
    return asyncio.run(coro)


class MeshCoreMessageTest(unittest.TestCase):
    def test_cyr2lat_transliterates_russian_text(self):
        self.assertEqual(
            cyr2lat("Авария: улица Южная", mode='full'),
            "Avariya: ulitsa Yuzhnaya",
        )

    def test_cyr2lat_soft_mode_replaces_only_similar_letters(self):
        self.assertEqual(
            cyr2lat("Авария: улица Южная", mode='soft'),
            "Aвapия: yлицa Южнaя",
        )

    def test_cyr2lat_off_mode_keeps_original_text(self):
        self.assertEqual(
            cyr2lat("Авария: улица Южная", mode='off'),
            "Авария: улица Южная",
        )

    def test_short_message_is_sent_as_single_payload(self):
        session = FakeSession()

        with contextlib.redirect_stdout(io.StringIO()):
            send_meshcore_message(session, "Авария", 133)

        self.assertEqual(session.messages, ["Aвapия"])

    def test_chunk_content_is_printed_before_send(self):
        session = FakeSession()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            send_meshcore_message(session, "Авария", 133)

        self.assertIn("MeshCore chunk 1/1: Aвapия", stdout.getvalue())

    def test_long_message_is_split_by_byte_limit(self):
        limit = 30
        messages = prepare_meshcore_messages("улица Южная " * 10, limit)

        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertLessEqual(len(message.encode("utf-8")), limit)

    def test_prepare_messages_can_skip_cyr2lat(self):
        self.assertEqual(
            prepare_meshcore_messages("Авария", 133, cyr2lat_mode='off'),
            ["Авария"],
        )

    def test_chunk_prefix_is_counted_inside_limit(self):
        limit = 12
        messages = prepare_meshcore_messages("aa bb cc dd ee ff gg hh", limit)

        self.assertGreater(len(messages), 1)
        for index, message in enumerate(messages, start=1):
            self.assertTrue(
                message.startswith("[" + str(index) + "/" + str(len(messages)) + "] ")
            )
            self.assertLessEqual(len(message.encode("utf-8")), limit)

    def test_delay_is_applied_between_chunks_only(self):
        session = FakeSession()

        with contextlib.redirect_stdout(io.StringIO()):
            with patch('start_meshcore_ha.time.sleep') as sleep:
                send_meshcore_message(session, "aa bb cc dd ee ff gg hh", 12, chunk_delay_ms=250)

        self.assertGreater(len(session.messages), 1)
        self.assertEqual(sleep.call_count, len(session.messages) - 1)
        sleep.assert_called_with(0.25)

    def test_post_delay_is_applied_between_messages_only(self):
        sent_messages = []
        send_message = create_delayed_send_message(sent_messages.append, 1000)

        with patch('start_meshcore_ha.time.sleep') as sleep:
            send_message("first")
            send_message("second")
            send_message("third")

        self.assertEqual(sent_messages, ["first", "second", "third"])
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(1.0)

    def test_post_delay_is_not_applied_for_single_message(self):
        sent_messages = []
        send_message = create_delayed_send_message(sent_messages.append, 1000)

        with patch('start_meshcore_ha.time.sleep') as sleep:
            send_message("first")

        self.assertEqual(sent_messages, ["first"])
        sleep.assert_not_called()

    def test_long_word_is_split_without_breaking_utf8_characters(self):
        limit = 15
        messages = prepare_meshcore_messages("😀" * 10, limit)

        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertLessEqual(len(message.encode("utf-8")), limit)

    def test_env_limit_defaults_to_133_bytes(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(parse_meshcore_message_limit(), 133)

    def test_env_limit_rejects_too_small_value(self):
        with patch.dict('os.environ', {'MESHCORE_MESSAGE_LIMIT_BYTES': '49'}):
            with self.assertRaises(ValueError):
                parse_meshcore_message_limit()

    def test_env_limit_rejects_non_integer_value(self):
        with patch.dict('os.environ', {'MESHCORE_MESSAGE_LIMIT_BYTES': 'small'}):
            with self.assertRaises(ValueError):
                parse_meshcore_message_limit()

    def test_env_cyr2lat_mode_defaults_to_soft(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(parse_meshcore_cyr2lat_mode(), 'soft')

    def test_env_cyr2lat_mode_accepts_full(self):
        with patch.dict('os.environ', {'MESHCORE_CYR2LAT_MODE': 'full'}):
            self.assertEqual(parse_meshcore_cyr2lat_mode(), 'full')

    def test_env_cyr2lat_mode_accepts_off(self):
        with patch.dict('os.environ', {'MESHCORE_CYR2LAT_MODE': 'off'}):
            self.assertEqual(parse_meshcore_cyr2lat_mode(), 'off')

    def test_env_cyr2lat_mode_rejects_unknown_value(self):
        with patch.dict('os.environ', {'MESHCORE_CYR2LAT_MODE': 'mixed'}):
            with self.assertRaises(ValueError):
                parse_meshcore_cyr2lat_mode()

    def test_env_chunk_delay_defaults_to_zero_ms(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(parse_meshcore_chunk_delay_ms(), 0)

    def test_env_chunk_delay_accepts_positive_integer(self):
        with patch.dict('os.environ', {'MESHCORE_CHUNK_DELAY_MS': '250'}):
            self.assertEqual(parse_meshcore_chunk_delay_ms(), 250)

    def test_env_chunk_delay_rejects_negative_value(self):
        with patch.dict('os.environ', {'MESHCORE_CHUNK_DELAY_MS': '-1'}):
            with self.assertRaises(ValueError):
                parse_meshcore_chunk_delay_ms()

    def test_env_chunk_delay_rejects_non_integer_value(self):
        with patch.dict('os.environ', {'MESHCORE_CHUNK_DELAY_MS': 'slow'}):
            with self.assertRaises(ValueError):
                parse_meshcore_chunk_delay_ms()

    def test_env_post_delay_defaults_to_1000_ms(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(parse_meshcore_post_delay_ms(), 1000)

    def test_env_post_delay_accepts_positive_integer(self):
        with patch.dict('os.environ', {'MESHCORE_POST_DELAY_MS': '2500'}):
            self.assertEqual(parse_meshcore_post_delay_ms(), 2500)

    def test_env_post_delay_accepts_zero(self):
        with patch.dict('os.environ', {'MESHCORE_POST_DELAY_MS': '0'}):
            self.assertEqual(parse_meshcore_post_delay_ms(), 0)

    def test_env_post_delay_rejects_negative_value(self):
        with patch.dict('os.environ', {'MESHCORE_POST_DELAY_MS': '-1'}):
            with self.assertRaises(ValueError):
                parse_meshcore_post_delay_ms()

    def test_env_post_delay_rejects_non_integer_value(self):
        with patch.dict('os.environ', {'MESHCORE_POST_DELAY_MS': 'slow'}):
            with self.assertRaises(ValueError):
                parse_meshcore_post_delay_ms()

    def test_env_tcp_host_is_required(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                parse_meshcore_tcp_host()

    def test_env_tcp_host_is_trimmed(self):
        with patch.dict('os.environ', {'MESHCORE_TCP_HOST': '  192.168.1.100  '}):
            self.assertEqual(parse_meshcore_tcp_host(), '192.168.1.100')

    def test_env_tcp_port_defaults_to_5000(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(parse_meshcore_tcp_port(), 5000)

    def test_env_tcp_port_rejects_non_integer_value(self):
        with patch.dict('os.environ', {'MESHCORE_TCP_PORT': 'tcp'}):
            with self.assertRaises(ValueError):
                parse_meshcore_tcp_port()

    def test_env_tcp_port_rejects_out_of_range_value(self):
        with patch.dict('os.environ', {'MESHCORE_TCP_PORT': '70000'}):
            with self.assertRaises(ValueError):
                parse_meshcore_tcp_port()

    def test_env_tcp_timeout_defaults_to_fifteen_seconds(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(parse_meshcore_tcp_timeout_seconds(), 15.0)

    def test_env_tcp_timeout_accepts_number(self):
        with patch.dict('os.environ', {'MESHCORE_TCP_TIMEOUT_SECONDS': '3.5'}):
            self.assertEqual(parse_meshcore_tcp_timeout_seconds(), 3.5)

    def test_env_tcp_timeout_rejects_non_positive_value(self):
        with patch.dict('os.environ', {'MESHCORE_TCP_TIMEOUT_SECONDS': '0'}):
            with self.assertRaises(ValueError):
                parse_meshcore_tcp_timeout_seconds()

    def test_env_meshcore_channel_defaults_to_five(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(parse_meshcore_channel(), 5)

    def test_env_meshcore_channel_accepts_integer(self):
        with patch.dict('os.environ', {'MESHCORE_CHANNEL': '2'}):
            self.assertEqual(parse_meshcore_channel(), 2)

    def test_env_meshcore_channel_rejects_negative_value(self):
        with patch.dict('os.environ', {'MESHCORE_CHANNEL': '-1'}):
            with self.assertRaises(ValueError):
                parse_meshcore_channel()

    def test_tcp_connection_uses_meshcore_tcp_transport(self):
        meshcore, error_event_type = asyncio_run(
            create_meshcore_tcp_connection('192.168.1.100', 4000, FakeMeshCore)
        )

        self.assertIsInstance(meshcore, FakeMeshCore)
        self.assertEqual(FakeMeshCore.host, '192.168.1.100')
        self.assertEqual(FakeMeshCore.port, 4000)
        self.assertEqual(FakeMeshCore.default_timeout, 15.0)
        self.assertEqual(error_event_type, 'error')

    def test_tcp_connection_raises_when_node_does_not_answer_appstart(self):
        with self.assertRaises(ConnectionError):
            asyncio_run(
                create_meshcore_tcp_connection(
                    '192.168.1.100',
                    4000,
                    FakeMeshCoreNoResponse,
                    timeout=1.5,
                )
            )

    def test_tcp_inbound_frame_marker_accepts_less_than_marker(self):
        self.assertEqual(find_first_meshcore_frame_marker(b"\x00\x3c\x01"), 1)

    def test_tcp_inbound_frame_marker_accepts_greater_than_marker(self):
        self.assertEqual(find_first_meshcore_frame_marker(b"\x00\x3e\x01"), 1)

    def test_tcp_message_is_sent_to_channel(self):
        meshcore = FakeMeshCore()

        with contextlib.redirect_stdout(io.StringIO()):
            asyncio_run(
                send_meshcore_tcp_message(
                    meshcore,
                    'error',
                    0,
                    "Авария",
                    133,
                )
            )

        self.assertEqual(meshcore.commands.messages, [(0, "Aвapия")])

    def test_tcp_message_prints_chunk_content(self):
        meshcore = FakeMeshCore()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            asyncio_run(
                send_meshcore_tcp_message(
                    meshcore,
                    'error',
                    0,
                    "Авария",
                    133,
                )
            )

        self.assertIn("MeshCore TCP chunk 1/1 to channel 0: Aвapия", stdout.getvalue())

    def test_tcp_chunk_delay_is_applied_between_chunks_only(self):
        meshcore = FakeMeshCore()

        with contextlib.redirect_stdout(io.StringIO()):
            with patch('start_meshcore_tcp.asyncio.sleep') as sleep:
                asyncio_run(
                    send_meshcore_tcp_message(
                        meshcore,
                        'error',
                        0,
                        "aa bb cc dd ee ff gg hh",
                        12,
                        chunk_delay_ms=250,
                    )
                )

        self.assertGreater(len(meshcore.commands.messages), 1)
        self.assertEqual(sleep.call_count, len(meshcore.commands.messages) - 1)
        sleep.assert_called_with(0.25)

    def test_tcp_send_raises_on_meshcore_error(self):
        result = SimpleNamespace(type='error', payload='failed')

        with self.assertRaises(RuntimeError):
            raise_for_meshcore_error(result, 'error', 'send channel message')


if __name__ == '__main__':
    unittest.main()
