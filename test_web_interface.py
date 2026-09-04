"""Focused regression tests for browser audio delivery."""

import io
import json
import queue
import socket
import unittest
import urllib.request
import wave

from web_interface import WebInterfaceServer


class BrowserAudioTests(unittest.TestCase):
    def setUp(self):
        self.server = WebInterfaceServer(lambda: None)
        # The transport unit does not need a listening socket. Mark the server
        # as active so publish_wav follows its normal production path.
        self.server._server = object()
        self.listener = queue.Queue()
        self.server.add_listener(self.listener)

    def test_published_audio_is_a_complete_wav_clip(self):
        pcm = b"\0\0" * 240

        audio_id = self.server.publish_wav(pcm, duration=0.01, volume=0.5)

        self.assertIsNotNone(audio_id)
        event, payload = self.listener.get_nowait()
        self.assertEqual(event, "audio")
        message = json.loads(payload)
        self.assertEqual(message["id"], audio_id)
        self.assertEqual(message["url"], f"/api/audio/{audio_id}.wav")
        self.assertEqual(message["volume"], 0.5)

        with wave.open(io.BytesIO(self.server.get_audio(audio_id)), "rb") as clip:
            self.assertEqual(clip.getnchannels(), 1)
            self.assertEqual(clip.getsampwidth(), 2)
            self.assertEqual(clip.getframerate(), 24000)
            self.assertEqual(clip.getnframes(), 240)

    def test_interrupt_unblocks_a_clip_waiter_without_marking_it_complete(self):
        audio_id = self.server.publish_wav(b"\0\0", duration=1 / 24000, volume=1)

        self.server.interrupt_audio()

        self.assertFalse(self.server.wait_for_audio(audio_id))

    def test_audio_endpoint_returns_a_finite_response(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        server = WebInterfaceServer(lambda: None)
        started, _ = server.start(port)
        self.assertTrue(started)
        listener = queue.Queue()
        server.add_listener(listener)
        try:
            audio_id = server.publish_wav(b"\0\0" * 12, duration=0.0005, volume=1)
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/audio/{audio_id}.wav"
            ) as response:
                content = response.read()
                self.assertEqual(response.headers["Content-Type"], "audio/wav")
                self.assertEqual(int(response.headers["Content-Length"]), len(content))
                self.assertEqual(content[:4], b"RIFF")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
