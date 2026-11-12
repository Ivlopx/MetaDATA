import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from radio_metadata.config import Config, ConfigStore
from radio_metadata.engine import Engine
from radio_metadata.model import Snapshot, inside, resolve
from radio_metadata.outputs import IcecastOutput, LocalOutput
from radio_metadata.sources import RadioBossSource, parse_playback
from radio_metadata.storage import History


def music(source="radioboss", **kwargs):
    values = dict(source=source, playing=True, artist="Björk", title="Jóga",
                  filename=r"C:\Musica\album\joga.mp3", kind="music")
    values.update(kwargs)
    return Snapshot(**values)


def xml(state="play", filename=r"C:\Musica\a.mp3"):
    return f'<Info><CurrentTrack><TRACK ARTIST="A" TITLE="B" FILENAME="{filename}" /></CurrentTrack><Playback state="{state}" /></Info>'.encode()


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(music_folders=[r"C:\Musica"], spotify_publish=True)

    def test_select_priority_then_filter_ad(self):
        result = resolve([music(title="Anuncio especial"), music("spotify")], self.config)
        self.assertIsNone(result.song)
        self.assertEqual(result.text, self.config.description or 'Sin reproducción')
        self.assertTrue(result.conflict)

    def test_switch_pause_and_manual_no_fallback(self):
        tracks = [music(playing=False), music("spotify")]
        self.assertEqual(resolve(tracks, self.config).source, "spotify")
        self.assertIsNone(resolve(tracks, self.config, "radioboss").song)
        self.assertIsNone(resolve(tracks, self.config, "station").song)

    def test_missing_metadata_unknown_type_and_placeholders(self):
        for track in [music(artist=""), music(title="Unknown title"), music("spotify", kind="unknown"),
                      music(kind="Commercial"), music(error="connection failed")]:
            with self.subTest(track=track):
                self.assertIsNone(resolve([track], self.config).song)

    def test_folders_are_boundary_aware_case_insensitive(self):
        self.assertTrue(inside(r"c:\MUSICA\a.mp3", self.config.music_folders))
        for filename in (r"C:\Musical\a.mp3", r"C:\Musica\..\Ads\a.mp3", "a.mp3", r"D:\Musica\a.mp3"):
            self.assertFalse(inside(filename, self.config.music_folders))
        config = replace(self.config, excluded_folders=[r"C:\Musica\album"])
        self.assertIsNone(resolve([music()], config).song)
        self.assertIsNone(resolve([music()], Config()).song)

    def test_keyword_boundaries_not_substrings(self):
        self.assertIsNotNone(resolve([music(title="Spotlight")], self.config).song)
        self.assertIsNone(resolve([music(title="Nuevo spot de radio")], self.config).song)

    def test_spotify_is_observation_only_by_default(self):
        self.assertIsNone(resolve([music("spotify")], Config()).song)

    def test_history_only_music_and_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = History(Path(tmp) / "history.db")
            song = resolve([music()], self.config)
            history.record(song)
            history.record(song)
            self.assertEqual(len(history.recent()), 1)
            history.record(resolve([music(title="Jingle")], self.config))
            self.assertEqual(len(history.recent()), 1)
            history.record(song)
            self.assertEqual(len(history.recent()), 2)
            self.assertRegex(history.recent()[0][0], r"[+-]\d\d:\d\d$")
            history.close()


class AdapterTests(unittest.TestCase):
    def test_radioboss_documented_xml_and_paused(self):
        track = parse_playback(xml())
        self.assertTrue(track.playing)
        self.assertEqual(track.artist, "A")
        for state in ("pause", "stop", "", "unknown"):
            self.assertFalse(parse_playback(xml(state)).playing)
        with self.assertRaises(ValueError):
            parse_playback(b"<Error/>")

    def test_xml_entities_rejected(self):
        with self.assertRaises(Exception):
            parse_playback(b'<!DOCTYPE a [<!ENTITY e SYSTEM "file:///etc/passwd">]><Info>&e;</Info>')

    def test_tags_and_race_protection(self):
        source = RadioBossSource(Config(music_folders=[r"C:\Musica"]))
        tags = b'<TagInfo><File TypeIdentifier="Commercial" Artwork_Base64="aGk="/></TagInfo>'
        with patch.object(source, "_request", side_effect=[xml(), tags, xml()]):
            result = asyncio.run(source.poll())
            self.assertEqual(result.kind, "Commercial")
            self.assertEqual(result.artwork, b"hi")
        with patch.object(source, "_request", side_effect=[xml(), tags, xml("stop")]):
            result = asyncio.run(source.poll())
            self.assertFalse(result.playing)
            self.assertTrue(result.error)

    def test_icecast_utf8_auth_and_application_failure(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, text="<iceresponse><message>Metadata update successful</message><return>1</return></iceresponse>")
        real_client = httpx.Client
        target = {"url": "https://radio.example", "mount": "/live", "username": "source", "password_env": "TEST_RADIO_PASS"}
        output = IcecastOutput(target)
        song = resolve([music()], Config(music_folders=[r"C:\Musica"]))
        with patch.dict(os.environ, TEST_RADIO_PASS="dummy-secret"), patch("radio_metadata.outputs.httpx.Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            self.assertIn("aceptada", output.send(song))
            self.assertEqual(requests[0].url.params["song"], "Björk - Jóga")
            self.assertEqual(requests[0].url.params["mount"], "/live")
            self.assertNotIn("dummy-secret", str(requests[0].url))
            self.assertTrue(requests[0].headers["Authorization"].startswith("Basic "))
            output.send(song)
            self.assertEqual(len(requests), 1)
        def denied(request):
            return httpx.Response(200, text="<iceresponse><return>0</return></iceresponse>")
        with patch.dict(os.environ, TEST_RADIO_PASS="dummy-secret"), patch("radio_metadata.outputs.httpx.Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(denied), **kw)):
            output.next_attempt = 0
            self.assertIn("Error", output.send(song))
            self.assertEqual(output.failures, 1)


class PersistenceTests(unittest.TestCase):
    def test_config_roundtrip_and_invalid_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            original = store.load()
            self.assertEqual(store.load(), original)
            with self.assertRaises(ValueError):
                store.save(replace(original, poll_seconds=0))
            self.assertEqual(store.load(), original)
            with self.assertRaises(ValueError):
                replace(original, radioboss_enabled="false").validate()

    def test_safe_outputs_clear_title_and_artwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(music_folders=[r"C:\Musica"])
            output = LocalOutput(Path(tmp))
            output.publish(resolve([music(artwork=b"\x89PNG\r\n\x1a\nimage")], config), config)
            state = json.loads((Path(tmp) / "nowplaying.json").read_text())
            self.assertTrue(state["artwork_file"])
            output.publish(resolve([music(title="Anuncio")], config), config)
            state = json.loads((Path(tmp) / "nowplaying.json").read_text())
            self.assertFalse(state["is_music"])
            self.assertEqual(state["artist"], "")
            self.assertEqual(state["artwork_file"], "")
            self.assertNotIn("Anuncio", (Path(tmp) / "nowplaying.txt").read_text())

    def test_demo_never_network_and_ad_never_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(Config(), Path(tmp), demo=True)
            with patch("httpx.Client", side_effect=AssertionError("No network in demo")), patch("httpx.AsyncClient", side_effect=AssertionError("No async network in demo")):
                result = asyncio.run(engine.tick())
                self.assertIsNotNone(result[0].song)
                engine.scenario = "ad"
                result = asyncio.run(engine.tick())
                self.assertIsNone(result[0].song)
                self.assertEqual(len(result[3]), 1)
                self.assertFalse((Path(tmp) / "output").exists())
            engine.close()

    def test_source_exception_clears_stale_song(self):
        class Broken:
            name = "radioboss"
            async def poll(self):
                raise RuntimeError("https://user:secret@host/?pass=secret")
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(Config(), Path(tmp))
            with patch("radio_metadata.engine.make_sources", return_value=[Broken()]):
                with self.assertLogs("radio_metadata.engine", level="WARNING") as logs:
                    decision, sources, _, rows = asyncio.run(engine.tick())
                self.assertNotIn("secret", "".join(logs.output))
                self.assertIsNone(decision.song)
                self.assertTrue(sources[0].error)
                self.assertEqual(rows, [])
            engine.close()

    def test_missing_windows_module_has_actionable_error_and_no_song(self):
        class Missing:
            name = "spotify"
            async def poll(self):
                raise ModuleNotFoundError("internal exception text", name="winrt.windows.foundation.collections")
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(Config(), Path(tmp))
            with patch("radio_metadata.engine.make_sources", return_value=[Missing()]):
                decision, sources, _, rows = asyncio.run(engine.tick())
            self.assertIsNone(decision.song)
            self.assertIn("winrt.windows.foundation.collections", sources[0].error)
            self.assertIn("instalar.bat", sources[0].error)
            self.assertNotIn("internal exception text", sources[0].error)
            self.assertEqual(rows, [])
            engine.close()

    def test_unknown_module_name_does_not_expose_sensitive_exception_data(self):
        class Missing:
            name = "spotify"
            async def poll(self):
                raise ModuleNotFoundError("secret message", name="https://user:secret@host")
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(Config(), Path(tmp))
            with patch("radio_metadata.engine.make_sources", return_value=[Missing()]):
                _, sources, _, _ = asyncio.run(engine.tick())
            self.assertNotIn("secret", sources[0].error)
            engine.close()


if __name__ == "__main__":
    unittest.main()
