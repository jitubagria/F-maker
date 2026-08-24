"""Slice 1 checks for safe, repeatable local-asset rendering."""
from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from app import create_app
from engine import (
    ConfigError,
    ROOT,
    _line_width,
    _wrap,
    draw_headline,
    headline_tokens,
    load_font,
    render,
    resolve_subject_photo,
    validate_config,
)


def build_fixture(root: Path) -> dict:
    """Create deliberately named local assets; no production library is touched."""
    (root / "templates").mkdir(parents=True)
    (root / "fonts").mkdir()
    (root / "cutouts" / "students").mkdir(parents=True)
    (root / "cutouts" / "empty").mkdir()
    (root / "cutouts" / "defaults").mkdir()
    Image.new("RGB", (400, 220), "#123456").save(root / "templates" / "northstar_bulletin.png")
    Image.new("RGBA", (160, 50), (255, 255, 255, 255)).save(root / "templates" / "northstar_logo.png")
    shutil.copy2(ROOT / "fonts" / "headline.ttf", root / "fonts" / "headline.ttf")
    for filename, color in (("faculty_zenith.png", (255, 100, 20, 255)), ("faculty_orbit.png", (20, 180, 255, 255)), ("sentinel_default.png", (230, 40, 130, 255))):
        target = root / "cutouts" / ("defaults" if filename == "sentinel_default.png" else "students") / filename
        Image.new("RGBA", (80, 150), color).save(target)
    return {
        "canvas": {"width": 400, "height": 220, "output_format": "webp", "output_quality": 90},
        "default_cutout": "cutouts/defaults/sentinel_default.png",
        "domains": {
            "northstaracademy": {
                "brand_color": "#123456", "brand_color_dark": "#102030", "highlight_color": "#FFD000", "text_color": "#FFFFFF",
                "logo": "templates/northstar_logo.png", "font": "fonts/headline.ttf",
                "templates": {
                    "bulletin": {
                        "background": "templates/northstar_bulletin.png",
                        "text_zone": [12, 35, 245, 135], "subtitle_zone": [12, 178, 245, 24],
                        "photo_zone": [270, 10, 120, 200], "photo_anchor": "bottom", "logo_zone": [12, 8, 100, 24],
                    }
                },
            }
        },
        "category_to_photo_folder": {
            "students": "cutouts/students", "empty": "cutouts/empty", "missing": "cutouts/not-created",
        },
    }


class EngineHardeningTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.config = build_fixture(self.root)

    def tearDown(self):
        self.workspace.cleanup()

    def test_phrase_highlighting_requires_an_exact_contiguous_run(self):
        # The first NEET is a known-bad case from the old token-membership logic.
        repeated = headline_tokens("NEET GUIDE NEET 2026 UPDATE", "NEET 2026")
        self.assertEqual([token.highlighted for token in repeated], [False, False, True, True, False])
        self.assertEqual([token.highlighted for token in headline_tokens("NEET 2026 RESULT", "NEET 2026")], [True, True, False])
        self.assertEqual([token.highlighted for token in headline_tokens("LATEST NEET 2026 RESULT", "NEET 2026")], [False, True, True, False])
        self.assertEqual([token.highlighted for token in headline_tokens("NEET RESULT UPDATE", "NEET")], [True, False, False])

    def test_concurrent_renders_keep_their_own_highlight_phrase(self):
        title = "ALPHA BETA GAMMA"
        def digest(highlight):
            image, _ = render("northstaracademy", "bulletin", "students", title, highlight, config=self.config, root=self.root)
            return hashlib.sha256(image.tobytes()).hexdigest()

        expected = {"ALPHA": digest("ALPHA"), "BETA": digest("BETA")}
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda highlight: (highlight, digest(highlight)), ["ALPHA", "BETA"] * 20))
        for highlight, image_digest in results:
            self.assertEqual(image_digest, expected[highlight])
        self.assertFalse(hasattr(draw_headline, "highlight"))

    def test_subject_resolution_is_deterministic_and_supports_shuffle(self):
        first = resolve_subject_photo("northstaracademy", "students", "AETHER SCHOLARSHIP UPDATE", config=self.config, root=self.root)
        second = resolve_subject_photo("northstaracademy", "students", "AETHER SCHOLARSHIP UPDATE", config=self.config, root=self.root)
        self.assertEqual(first.path, second.path)
        choices = {
            resolve_subject_photo("northstaracademy", "students", "AETHER SCHOLARSHIP UPDATE", shuffle=f"shuffle-{index}", config=self.config, root=self.root).path
            for index in range(12)
        }
        self.assertGreater(len(choices), 1, "Distinct shuffle values must be capable of selecting another asset")

    def test_empty_missing_default_and_missing_explicit_photo_all_warn(self):
        empty = resolve_subject_photo("northstaracademy", "empty", "EMPTY CATEGORY", config=self.config, root=self.root)
        self.assertTrue(empty.has_warning)
        self.assertTrue(empty.path.endswith("sentinel_default.png"))
        self.assertIn("No photo found for category 'empty'", empty.warning_message)

        missing = resolve_subject_photo("northstaracademy", "missing", "MISSING CATEGORY", config=self.config, root=self.root)
        self.assertTrue(missing.has_warning)
        self.assertTrue(missing.path.endswith("sentinel_default.png"))

        explicit_missing = resolve_subject_photo(
            "northstaracademy", "students", "EXPLICIT MISSING", photo="cutouts/students/not-in-library.png", config=self.config, root=self.root,
        )
        self.assertTrue(explicit_missing.has_warning)
        self.assertIsNotNone(explicit_missing.path)
        self.assertIn("Requested photo", explicit_missing.warning_message)

        with self.assertRaisesRegex(ValueError, "inside the cutouts library"):
            resolve_subject_photo(
                "northstaracademy", "students", "UNSAFE EXPLICIT", photo="templates/northstar_bulletin.png", config=self.config, root=self.root,
            )

        no_default_config = copy.deepcopy(self.config)
        no_default_config.pop("default_cutout")
        no_default = resolve_subject_photo("northstaracademy", "empty", "NO DEFAULT", config=no_default_config, root=self.root)
        self.assertTrue(no_default.has_warning)
        self.assertIsNone(no_default.path)
        self.assertIn("rendering without a subject", no_default.warning_message)

    def test_config_validation_rejects_bad_zones_and_warns_for_missing_category_folder(self):
        warnings = validate_config(self.config, self.root)
        self.assertIn("Category 'missing' has no usable cutout folder", warnings[0])
        bad_config = copy.deepcopy(self.config)
        bad_config["domains"]["northstaracademy"]["templates"]["bulletin"]["text_zone"] = [12, 35, 999, 135]
        with self.assertRaisesRegex(ConfigError, r"domains\.northstaracademy\.templates\.bulletin\.text_zone"):
            validate_config(bad_config, self.root)
        missing_required = copy.deepcopy(self.config)
        del missing_required["domains"]["northstaracademy"]["font"]
        with self.assertRaisesRegex(ConfigError, r"domains\.northstaracademy\.font is required"):
            validate_config(missing_required, self.root)
        missing_background = copy.deepcopy(self.config)
        missing_background["domains"]["northstaracademy"]["templates"]["bulletin"]["background"] = "templates/not-present.png"
        with self.assertRaisesRegex(ConfigError, r"background file is missing"):
            validate_config(missing_background, self.root)

    def test_long_word_is_hard_broken_before_rendering(self):
        long_token = "HYPERCOMMUNICATION" * 100
        image, _ = render("northstaracademy", "bulletin", "students", long_token, config=self.config, root=self.root)
        self.assertEqual(image.size, (400, 220))  # real render completes with the original canvas bounds
        draw = ImageDraw.Draw(image)
        font = load_font("fonts/headline.ttf", 27, self.root)
        lines = _wrap(draw, headline_tokens(long_token, ""), font, 245, int(27 * 0.30))
        self.assertTrue(lines)
        self.assertTrue(all(_line_width(draw, line, font, int(27 * 0.30)) <= 245 for line in lines))


class ApiWarningTests(unittest.TestCase):
    def test_preview_exposes_fixture_empty_category_warning_in_headers(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            config = build_fixture(root)
            client = create_app().test_client()
            # app.render is patched to the real engine with a deliberately empty fixture category.
            def fixture_render(**payload):
                return render(**payload, config=config, root=root)

            with patch("app.render", side_effect=fixture_render):
                response = client.post("/api/preview", json={
                    "domain": "northstaracademy", "template": "bulletin", "category": "empty",
                    "title": "EMPTY SUBJECT FALLBACK", "highlight": "EMPTY",
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["X-Fmaker-Subject-Warning"], "true")
            self.assertIn("No photo found for category 'empty'", response.headers["X-Fmaker-Subject-Warning-Message"])


if __name__ == "__main__":
    unittest.main()
