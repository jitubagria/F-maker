"""Isolated checks for editable template backgrounds and placement zones."""
from __future__ import annotations

from io import BytesIO
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import create_app, template_payload, update_template_zones
from engine import ConfigError
from test_engine import build_fixture


def png_stream(color):
    stream = BytesIO()
    Image.new("RGB", (240, 120), color).save(stream, "PNG")
    stream.seek(0)
    return stream


class TemplateLibraryTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.config = build_fixture(self.root)
        (self.root / "config").mkdir()

    def tearDown(self):
        self.workspace.cleanup()

    def test_template_payload_exposes_preview_and_all_editable_zones(self):
        payload = template_payload(self.config)
        template = payload["domains"][0]["templates"][0]
        self.assertEqual(template["background_url"], "/template-background/northstaracademy/bulletin")
        self.assertEqual(set(template["zones"]), {"text_zone", "subtitle_zone", "photo_zone", "logo_zone"})

    def test_zone_change_is_validated_before_it_can_be_saved(self):
        zones = copy.deepcopy(self.config["domains"]["northstaracademy"]["templates"]["bulletin"])
        updated = update_template_zones("northstaracademy", "bulletin", zones, self.config, self.root)
        self.assertEqual(updated["domains"]["northstaracademy"]["templates"]["bulletin"]["photo_zone"], [270, 10, 120, 200])

        known_bad = copy.deepcopy(zones)
        known_bad["text_zone"] = [12, 35, 900, 135]
        with self.assertRaisesRegex(ConfigError, r"text_zone must stay within"):
            update_template_zones("northstaracademy", "bulletin", known_bad, self.config, self.root)
        with self.assertRaisesRegex(ValueError, "subtitle_zone"):
            update_template_zones("northstaracademy", "bulletin", {"text_zone": [1, 1, 1, 1]}, self.config, self.root)

    def test_background_upload_replaces_only_the_declared_png_in_an_isolated_workspace(self):
        original = (self.root / "templates" / "northstar_bulletin.png").read_bytes()
        with patch("app.APP_ROOT", self.root), patch.dict("app.CFG", self.config, clear=True):
            response = create_app().test_client().post(
                "/api/templates/northstaracademy/bulletin/background",
                data={"background": (png_stream("orange"), "new-layout.png")},
            )
        self.assertEqual(response.status_code, 200)
        replaced = self.root / "templates" / "northstar_bulletin.png"
        self.assertNotEqual(replaced.read_bytes(), original)
        with Image.open(replaced) as image:
            self.assertEqual(image.size, (240, 120))

    def test_zone_endpoint_persists_a_validated_config_in_an_isolated_workspace(self):
        zones = {
            "text_zone": [14, 36, 240, 130], "subtitle_zone": [14, 178, 240, 24],
            "photo_zone": [270, 10, 120, 200], "logo_zone": [12, 8, 100, 24],
        }
        with patch("app.APP_ROOT", self.root), patch.dict("app.CFG", self.config, clear=True):
            response = create_app().test_client().put(
                "/api/templates/northstaracademy/bulletin/zones", json={"zones": zones},
            )
        self.assertEqual(response.status_code, 200)
        saved = (self.root / "config" / "templates.json").read_text(encoding="utf-8")
        self.assertIn('"text_zone": [', saved)
        self.assertIn("240", saved)


if __name__ == "__main__":
    unittest.main()
