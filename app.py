"""Local web editor for the config-driven featured-image generator."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import re

from flask import Flask, jsonify, request, send_file, send_from_directory

from engine import CFG, ROOT, generate, render

APP_ROOT = Path(ROOT)
OUTPUT_DIR = APP_ROOT / "output" / "exports"


def public_config():
    domains = {}
    for key, domain in CFG["domains"].items():
        domains[key] = {
            "name": key,
            "brand_color": domain["brand_color"],
            "highlight_color": domain["highlight_color"],
            "templates": list(domain["templates"].keys()),
        }
    return {"canvas": CFG["canvas"], "domains": domains,
            "categories": sorted(CFG["category_to_photo_folder"].keys())}


def available_photos(root=APP_ROOT):
    photos = []
    root = Path(root)
    for path in sorted((root / "cutouts").glob("**/*.png")):
        photos.append(path.relative_to(root).as_posix())
    return photos


def stats_payload(config=CFG, root=APP_ROOT, output_dir=OUTPUT_DIR):
    """Return filesystem-derived dashboard counts without changing any assets."""
    root = Path(root)
    output_dir = Path(output_dir)
    by_category = {}
    for category, folder in config["category_to_photo_folder"].items():
        category_dir = root / folder
        by_category[category] = len(list(category_dir.glob("*.png"))) if category_dir.is_dir() else 0
    return {
        "brands": len(config["domains"]),
        "templates": sum(len(domain["templates"]) for domain in config["domains"].values()),
        "cutouts_by_category": by_category,
        "total_cutouts": sum(by_category.values()),
        "total_exports": len(list(output_dir.glob("*.webp"))) if output_dir.is_dir() else 0,
    }


def payload():
    body = request.get_json(silent=True) or {}
    return {
        "domain": str(body.get("domain", "matrixedu")),
        "template": str(body.get("template", "news")),
        "category": str(body.get("category", "news")),
        "title": str(body.get("title", "")),
        "highlight": str(body.get("highlight", "")),
        "subtitle": str(body.get("subtitle", "")),
        "photo": body.get("photo") or None,
        "shuffle": body.get("shuffle") or None,
    }


def add_subject_warning(response, subject):
    """Expose non-fatal photo fallbacks without changing the PNG preview body."""
    response.headers["X-Fmaker-Subject-Warning"] = "true" if subject.has_warning else "false"
    if subject.warning_message:
        response.headers["X-Fmaker-Subject-Warning-Message"] = subject.warning_message
    return response


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:52] or "featured-image"


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    @app.get("/")
    def home():
        return send_from_directory(APP_ROOT / "static", "index.html")

    @app.get("/api/config")
    def config():
        return jsonify(public_config())

    @app.get("/api/photos")
    def photos():
        return jsonify({"photos": available_photos()})

    @app.get("/api/stats")
    def stats():
        return jsonify(stats_payload())

    @app.post("/api/preview")
    def preview():
        try:
            data = payload()
            image, subject = render(**data)
        except (ValueError, KeyError) as error:
            return jsonify({"error": str(error)}), 400
        stream = BytesIO()
        image.convert("RGB").save(stream, "PNG")
        stream.seek(0)
        return add_subject_warning(send_file(stream, mimetype="image/png", max_age=0), subject)

    @app.post("/api/export")
    def export():
        try:
            data = payload()
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{slug(data['title'])}-{uuid4().hex[:8]}.webp"
            webp, png, subject = generate(**{**data, "out": str(OUTPUT_DIR / filename)})
        except (ValueError, KeyError) as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({
            "webp": f"/exports/{Path(webp).name}",
            "png": f"/exports/{Path(png).name}",
            "subject_warning": subject.has_warning,
            "subject_warning_message": subject.warning_message,
        })

    @app.get("/exports/<path:filename>")
    def exports(filename):
        return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5050)
