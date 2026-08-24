"""Isolated checks for category-only raw and cutout asset management."""
from __future__ import annotations

from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import asset_payload, create_app


def png_upload_bytes(color=(45, 120, 220, 255)):
    stream = BytesIO()
    Image.new("RGBA", (24, 32), color).save(stream, "PNG")
    stream.seek(0)
    return stream


class AssetLibraryTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.app_root = patch("app.APP_ROOT", self.root)
        self.app_root.start()
        self.client = create_app().test_client()

    def tearDown(self):
        self.app_root.stop()
        self.workspace.cleanup()

    def test_creates_category_and_lists_only_its_direct_cutouts(self):
        response = self.client.post("/api/assets/create-category", json={"category": "orbit-faculty"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue((self.root / "raw_photos" / "orbit-faculty").is_dir())
        self.assertTrue((self.root / "cutouts" / "orbit-faculty").is_dir())
        Image.new("RGBA", (8, 8)).save(self.root / "cutouts" / "orbit-faculty" / "mentor.png")
        Image.new("RGBA", (8, 8)).save(self.root / "cutouts" / "orbit-faculty" / "nested.png")
        payload = asset_payload(self.root)
        self.assertEqual(payload["model"], "u2net_human_seg")
        self.assertEqual(payload["categories"][0]["name"], "orbit-faculty")
        self.assertEqual([item["name"] for item in payload["categories"][0]["cutouts"]], ["mentor.png", "nested.png"])

    def test_upload_uses_configured_model_and_delete_keeps_raw(self):
        def fake_cutout(source, target, model, alpha_matting=False):
            self.assertEqual(model, "u2net_human_seg")
            self.assertFalse(alpha_matting)
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (12, 18), (0, 220, 120, 180)).save(target)

        with patch("app.process_cutout", side_effect=fake_cutout) as cut:
            response = self.client.post("/api/assets/upload", data={
                "category": "staff-omega",
                "photo": (png_upload_bytes(), "Dr. Nova.png"),
            })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(cut.call_count, 1)
        self.assertTrue((self.root / "raw_photos" / "staff-omega" / "Dr-Nova.png").is_file())
        self.assertTrue((self.root / "cutouts" / "staff-omega" / "Dr-Nova.png").is_file())
        deleted = self.client.delete("/api/assets/staff-omega/Dr-Nova.png")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse((self.root / "cutouts" / "staff-omega" / "Dr-Nova.png").exists())
        self.assertTrue((self.root / "raw_photos" / "staff-omega" / "Dr-Nova.png").is_file())

    def test_recut_reads_matching_raw_and_passes_alpha_matting(self):
        raw = self.root / "raw_photos" / "orbit"
        raw.mkdir(parents=True)
        Image.new("RGB", (20, 20), "navy").save(raw / "speaker.jpg")
        calls = []

        def fake_cutout(source, target, model, alpha_matting=False):
            calls.append((Path(source).name, Path(target).name, model, alpha_matting))
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (8, 8)).save(target)

        with patch("app.process_cutout", side_effect=fake_cutout):
            response = self.client.post("/api/assets/recut", json={"category": "orbit", "file": "speaker.png", "alpha_matting": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [("speaker.jpg", "speaker.png", "u2net_human_seg", True)])

    def test_rejects_path_traversal_and_non_images(self):
        category = self.client.post("/api/assets/create-category", json={"category": "../escape"})
        self.assertEqual(category.status_code, 400)
        upload = self.client.post("/api/assets/upload", data={"category": "safe", "photo": (BytesIO(b"not an image"), "unsafe.jpg")})
        self.assertEqual(upload.status_code, 400)
        delete = self.client.delete("/api/assets/safe/../escape.png")
        self.assertEqual(delete.status_code, 400)


if __name__ == "__main__":
    unittest.main()
