"""Focused regression tests for browser audio delivery."""

import io
import json
import os
import queue
import shutil
import socket
import unittest
import urllib.request
import wave
from unittest import mock

import web_interface
from web_interface import _HLS_BYTES_PER_SECOND, _HLSStream, WebInterfaceServer


class BrowserAudioTests(unittest.TestCase):
    def setUp(self):
        self.server = WebInterfaceServer(lambda: None)
        # The transport unit does not need a listening socket. Mark the server
        # as active so publish_wav follows its normal production path.
        self.server._server = object()
        self.listener = queue.Queue()
        self.server.add_listener(self.listener)

    @unittest.skipUnless(os.path.isfile("/usr/bin/ffmpeg"), "Linux FFmpeg is required")
    def test_ffmpeg_lookup_survives_a_reduced_desktop_launcher_path(self):
        with mock.patch("web_interface.shutil.which", return_value=None):
            self.assertEqual(web_interface._ffmpeg_executable(), "/usr/bin/ffmpeg")

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

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for HLS encoding")
    def test_hls_stream_buffers_native_player_segments(self):
        stream = _HLSStream(generation=1, ffmpeg_path=shutil.which("ffmpeg"))
        stream.append(b"\0\0" * round(_HLS_BYTES_PER_SECOND * 6 / 2))
        stream.close()

        playlist = stream.playlist(timeout=30)

        self.assertIsNotNone(playlist)
        text = playlist.decode("utf-8")
        self.assertIn("#EXTM3U", text)
        self.assertIn("#EXT-X-ENDLIST", text)
        self.assertIn('/init.mp4"', text)
        self.assertIn("/segment/0.m4s", text)
        self.assertEqual(stream.initialization()[4:8], b"ftyp")
        self.assertEqual(stream.segment(0)[4:8], b"styp")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for HLS encoding")
    def test_hls_endpoints_serve_a_playlist_and_mp4_audio_segments(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        server = WebInterfaceServer(lambda: None)
        started, _ = server.start(port)
        self.assertTrue(started)
        try:
            self.assertTrue(server.set_audio_capabilities(True)["hls"])
            playlist_url = server.prepare_hls_audio()
            self.assertIsNotNone(playlist_url)
            self.assertTrue(
                server.append_hls_audio(
                    b"\0\0" * round(_HLS_BYTES_PER_SECOND * 6 / 2)
                )
            )
            server.finish_hls_audio()
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{playlist_url}"
            ) as response:
                playlist = response.read().decode("utf-8")
                self.assertEqual(
                    response.headers["Content-Type"],
                    "application/vnd.apple.mpegurl",
                )
            init_path = next(
                line.split('URI="', 1)[1].removesuffix('"')
                for line in playlist.splitlines()
                if line.startswith("#EXT-X-MAP:")
            )
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{init_path}"
            ) as response:
                self.assertEqual(response.headers["Content-Type"], "audio/mp4")
                self.assertEqual(response.read()[4:8], b"ftyp")
            segment_path = next(line for line in playlist.splitlines() if line.endswith(".m4s"))
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{segment_path}"
            ) as response:
                self.assertEqual(response.headers["Content-Type"], "video/iso.segment")
                self.assertEqual(response.read()[4:8], b"styp")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
