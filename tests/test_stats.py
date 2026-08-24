import tempfile
import unittest
from pathlib import Path

from app import stats_payload


class DashboardStatsTests(unittest.TestCase):
    def test_counts_categories_cutouts_and_webp_exports_from_an_isolated_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            (root / "cutouts" / "students").mkdir(parents=True)
            (root / "cutouts" / "sports").mkdir()
            (root / "output" / "exports").mkdir(parents=True)
            for name in ("atlas.png", "beacon.png"):
                (root / "cutouts" / "students" / name).write_bytes(b"png")
            (root / "cutouts" / "sports" / "comet.png").write_bytes(b"png")
            (root / "output" / "exports" / "feature.webp").write_bytes(b"webp")
            (root / "output" / "exports" / "feature.png").write_bytes(b"png")
            config = {
                "domains": {"alpha": {"templates": {"news": {}, "guide": {}}}, "beta": {"templates": {"news": {}}}},
                "category_to_photo_folder": {"students": "cutouts/students", "sports": "cutouts/sports", "campus": "cutouts/campus"},
            }
            stats = stats_payload(config, root, root / "output" / "exports")
            self.assertEqual(stats, {
                "brands": 2, "templates": 3,
                "cutouts_by_category": {"students": 2, "sports": 1, "campus": 0},
                "total_cutouts": 3, "total_exports": 1,
            })


if __name__ == "__main__":
    unittest.main()
