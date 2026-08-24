import tempfile
import unittest
from pathlib import Path

from app import delete_export_pair, list_exports


class ExportLibraryTests(unittest.TestCase):
    def test_lists_webp_exports_with_png_thumbnail_and_deletes_the_pair(self):
        with tempfile.TemporaryDirectory() as workspace:
            exports = Path(workspace)
            (exports / "aurora-guide.webp").write_bytes(b"webp")
            (exports / "aurora-guide.png").write_bytes(b"png")
            (exports / "orphan.png").write_bytes(b"png")
            items = list_exports(exports)
            self.assertEqual([item["name"] for item in items], ["aurora-guide.webp"])
            self.assertEqual(items[0]["thumb_url"], "/exports/aurora-guide.png")
            self.assertEqual(delete_export_pair("aurora-guide.webp", exports), ["aurora-guide.webp", "aurora-guide.png"])
            self.assertFalse((exports / "aurora-guide.webp").exists())
            self.assertTrue((exports / "orphan.png").exists())

    def test_rejects_paths_outside_the_export_folder(self):
        with tempfile.TemporaryDirectory() as workspace:
            with self.assertRaisesRegex(ValueError, "single .webp or .png"):
                delete_export_pair("../outside.webp", Path(workspace))


if __name__ == "__main__":
    unittest.main()
