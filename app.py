"""Local web editor for the config-driven featured-image generator."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
import re

from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image, UnidentifiedImageError

from engine import CFG, ROOT, generate, render

APP_ROOT = Path(ROOT)
OUTPUT_DIR = APP_ROOT / "output" / "exports"
RAW_PHOTOS_DIR = APP_ROOT / "raw_photos"
CUTOUTS_DIR = APP_ROOT / "cutouts"
MAX_ASSET_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
CATEGORY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


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


def _safe_export_name(filename):
    candidate = Path(filename)
    if candidate.name != filename or candidate.suffix.lower() not in {".webp", ".png"}:
        raise ValueError("Export filename must be a single .webp or .png file")
    return candidate.name


def list_exports(output_dir=OUTPUT_DIR):
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return []
    exports = []
    for webp in sorted(output_dir.glob("*.webp"), key=lambda path: path.stat().st_mtime, reverse=True):
        modified = datetime.fromtimestamp(webp.stat().st_mtime, tz=timezone.utc).isoformat()
        png = webp.with_suffix(".png")
        exports.append({
            "name": webp.name,
            "size": webp.stat().st_size,
            "modified": modified,
            "url": f"/exports/{webp.name}?download=1",
            "thumb_url": f"/exports/{png.name}" if png.is_file() else None,
        })
    return exports


def delete_export_pair(filename, output_dir=OUTPUT_DIR):
    name = _safe_export_name(filename)
    output_dir = Path(output_dir).resolve()
    requested = (output_dir / name).resolve()
    if output_dir not in requested.parents:
        raise ValueError("Export filename is outside the exports folder")
    stem = requested.with_suffix("")
    targets = [stem.with_suffix(".webp"), stem.with_suffix(".png")]
    removed = []
    for target in targets:
        if target.is_file():
            target.unlink()
            removed.append(target.name)
    if not removed:
        raise FileNotFoundError("Export was not found")
    return removed


def _safe_category(category):
    value = str(category or "").strip().lower()
    if not CATEGORY_PATTERN.fullmatch(value):
        raise ValueError("Category must use lowercase letters, numbers, hyphens, or underscores")
    return value


def _safe_cutout_name(filename):
    candidate = Path(str(filename or ""))
    if candidate.name != str(filename) or candidate.suffix.lower() != ".png":
        raise ValueError("Asset filename must be a single PNG filename")
    return candidate.name


def _category_directory(root, collection, category):
    base = (Path(root) / collection).resolve()
    target = (base / _safe_category(category)).resolve()
    if base not in target.parents:
        raise ValueError("Asset category is outside the local library")
    return target


def _source_image_name(upload_name):
    candidate = Path(str(upload_name or ""))
    if candidate.name != str(upload_name) or candidate.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("Only JPG, JPEG, and PNG image files are accepted")
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", candidate.stem).strip("-_")[:80]
    if not stem:
        raise ValueError("Image filename must contain letters or numbers")
    return f"{stem}{candidate.suffix.lower()}"


def _cutout_name_from_source(source_name):
    return f"{Path(source_name).stem}.png"


def asset_payload(root=APP_ROOT):
    """List the local, category-only source and transparent asset library."""
    root = Path(root)
    raw_root = root / "raw_photos"
    cutouts_root = root / "cutouts"
    categories = set()
    for library in (raw_root, cutouts_root):
        if library.is_dir():
            categories.update(path.name for path in library.iterdir() if path.is_dir())
    result = []
    for category in sorted(categories):
        try:
            raw_dir = _category_directory(root, "raw_photos", category)
            cutout_dir = _category_directory(root, "cutouts", category)
        except ValueError:
            continue
        raw_stems = {path.stem for path in raw_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES} if raw_dir.is_dir() else set()
        cutouts = []
        if cutout_dir.is_dir():
            for path in sorted(cutout_dir.glob("*.png")):
                cutouts.append({
                    "name": path.name,
                    "has_raw": path.stem in raw_stems,
                    "url": f"/assets/{category}/{path.name}",
                })
        result.append({"name": category, "raw_count": len(raw_stems), "cutouts": cutouts})
    return {"categories": result, "model": CFG["rembg_model"]}


def process_cutout(source, target, model, alpha_matting=False):
    """Run the one configured rembg model and write a transparent PNG."""
    from rembg import new_session, remove

    session = new_session(model)
    with Image.open(source) as image:
        result = remove(image.convert("RGBA"), session=session, alpha_matting=alpha_matting)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.save(target, "PNG")


def _validate_uploaded_image(upload):
    if not upload or not upload.filename:
        raise ValueError("Choose an image to upload")
    source_name = _source_image_name(upload.filename)
    upload.stream.seek(0, 2)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size > MAX_ASSET_UPLOAD_BYTES:
        raise ValueError("Image exceeds the 10 MB upload limit")
    try:
        with Image.open(upload.stream) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("Uploaded file is not a valid image") from error
    upload.stream.seek(0)
    return source_name


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

    @app.get("/api/assets")
    def asset_list():
        return jsonify(asset_payload())

    @app.post("/api/assets/create-category")
    def asset_create_category():
        try:
            category = _safe_category((request.get_json(silent=True) or {}).get("category"))
            _category_directory(APP_ROOT, "raw_photos", category).mkdir(parents=True, exist_ok=True)
            _category_directory(APP_ROOT, "cutouts", category).mkdir(parents=True, exist_ok=True)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"category": category}), 201

    @app.post("/api/assets/upload")
    def asset_upload():
        try:
            category = _safe_category(request.form.get("category"))
            upload = request.files.get("photo")
            source_name = _validate_uploaded_image(upload)
            raw_dir = _category_directory(APP_ROOT, "raw_photos", category)
            cutout_dir = _category_directory(APP_ROOT, "cutouts", category)
            raw_path = raw_dir / source_name
            cutout_path = cutout_dir / _cutout_name_from_source(source_name)
            if raw_path.exists() or cutout_path.exists():
                raise ValueError("An asset with this filename already exists in that category")
            raw_dir.mkdir(parents=True, exist_ok=True)
            upload.save(raw_path)
            process_cutout(raw_path, cutout_path, CFG["rembg_model"])
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            return jsonify({"error": f"Cutout could not be created: {error}"}), 500
        return jsonify({"category": category, "asset": {"name": cutout_path.name, "has_raw": True, "url": f"/assets/{category}/{cutout_path.name}"}}), 201

    @app.post("/api/assets/recut")
    def asset_recut():
        try:
            data = request.get_json(silent=True) or {}
            category = _safe_category(data.get("category"))
            cutout_name = _safe_cutout_name(data.get("file"))
            raw_dir = _category_directory(APP_ROOT, "raw_photos", category)
            cutout_dir = _category_directory(APP_ROOT, "cutouts", category)
            sources = [path for path in raw_dir.glob(f"{Path(cutout_name).stem}.*") if path.suffix.lower() in IMAGE_SUFFIXES]
            if len(sources) != 1:
                raise ValueError("The original source photo for this cutout was not found")
            process_cutout(sources[0], cutout_dir / cutout_name, CFG["rembg_model"], bool(data.get("alpha_matting")))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            return jsonify({"error": f"Cutout could not be reprocessed: {error}"}), 500
        return jsonify({"category": category, "asset": {"name": cutout_name, "has_raw": True, "url": f"/assets/{category}/{cutout_name}"}})

    @app.delete("/api/assets/<category>/<path:filename>")
    def asset_delete(category, filename):
        try:
            cutout_dir = _category_directory(APP_ROOT, "cutouts", category)
            target = (cutout_dir / _safe_cutout_name(filename)).resolve()
            if cutout_dir.resolve() not in target.parents or not target.is_file():
                raise FileNotFoundError("Cutout was not found")
            target.unlink()
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except FileNotFoundError as error:
            return jsonify({"error": str(error)}), 404
        return jsonify({"removed": target.name})

    @app.get("/assets/<category>/<path:filename>")
    def asset_file(category, filename):
        try:
            cutout_dir = _category_directory(APP_ROOT, "cutouts", category)
            name = _safe_cutout_name(filename)
        except ValueError:
            return jsonify({"error": "Cutout was not found"}), 404
        return send_from_directory(cutout_dir, name)

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
            "webp": f"/exports/{Path(webp).name}?download=1",
            "png": f"/exports/{Path(png).name}?download=1",
            "subject_warning": subject.has_warning,
            "subject_warning_message": subject.warning_message,
        })

    @app.get("/api/exports")
    def export_list():
        return jsonify(list_exports())

    @app.delete("/api/exports/<path:filename>")
    def export_delete(filename):
        try:
            removed = delete_export_pair(filename)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except FileNotFoundError as error:
            return jsonify({"error": str(error)}), 404
        return jsonify({"removed": removed})

    @app.get("/exports/<path:filename>")
    def exports(filename):
        try:
            name = _safe_export_name(filename)
        except ValueError:
            return jsonify({"error": "Export file was not found"}), 404
        return send_from_directory(OUTPUT_DIR, name, as_attachment=request.args.get("download") == "1")

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5050)
