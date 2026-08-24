"""Isolated checks for JSON-backed brand theme CRUD."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import brand_payload, create_app, create_brand, delete_brand, update_brand
from engine import ConfigError
from test_engine import build_fixture


def brand_data(**overrides):
    data = {
        "based_on": "northstaracademy", "brand_color": "#345678", "brand_color_dark": "#123456",
        "highlight_color": "#FEDC00", "text_color": "#FFFFFF", "logo": "templates/northstar_logo.png",
        "font": "fonts/headline.ttf", "default_cutout": "cutouts/defaults/sentinel_default.png",
    }
    data.update(overrides)
    return data


class BrandThemeTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.config = build_fixture(self.root)
        (self.root / "config").mkdir()

    def tearDown(self):
        self.workspace.cleanup()

    def test_create_clones_layout_but_keeps_brand_values_as_data(self):
        updated = create_brand("orbit-campus", brand_data(), self.config, self.root)
        created = updated["domains"]["orbit-campus"]
        self.assertEqual(created["brand_color"], "#345678")
        self.assertEqual(created["templates"], self.config["domains"]["northstaracademy"]["templates"])
        self.assertEqual(updated["default_cutout"], "cutouts/defaults/sentinel_default.png")
        payload = brand_payload(updated)
        self.assertEqual([brand["name"] for brand in payload["brands"]], ["northstaracademy", "orbit-campus"])

    def test_bad_brand_data_is_detected_before_a_config_can_be_saved(self):
        with self.assertRaisesRegex(ConfigError, r"brand_color must be a #RRGGBB color"):
            create_brand("orbit-campus", brand_data(brand_color="blue"), self.config, self.root)
        with self.assertRaisesRegex(ValueError, "already exists"):
            create_brand("northstaracademy", brand_data(), self.config, self.root)

    def test_update_and_delete_are_safe(self):
        two_brands = create_brand("orbit-campus", brand_data(), self.config, self.root)
        edited = update_brand("orbit-campus", brand_data(text_color="#000000"), two_brands, self.root)
        self.assertEqual(edited["domains"]["orbit-campus"]["text_color"], "#000000")
        reduced = delete_brand("orbit-campus", edited, self.root)
        self.assertNotIn("orbit-campus", reduced["domains"])
        with self.assertRaisesRegex(ValueError, "at least one"):
            delete_brand("northstaracademy", self.config, self.root)

    def test_create_endpoint_persists_and_returns_the_new_domain(self):
        request_data = brand_data(name="orbit-campus")
        with patch("app.APP_ROOT", self.root), patch.dict("app.CFG", copy.deepcopy(self.config), clear=True):
            client = create_app().test_client()
            response = client.post("/api/brands", json=request_data)
            picker = client.get("/api/config").get_json()
        self.assertEqual(response.status_code, 201)
        self.assertIn("orbit-campus", [item["name"] for item in response.get_json()["brands"]])
        self.assertIn("orbit-campus", picker["domains"])
        self.assertIn("orbit-campus", (self.root / "config" / "templates.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
