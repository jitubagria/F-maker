"""Config-driven featured-image compositor.

The renderer only reads approved local assets: template/logo/font files declared
in the config and transparent PNG subjects from ``cutouts/<category>``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "templates.json"
REQUIRED_DOMAIN_KEYS = (
    "brand_color", "brand_color_dark", "highlight_color", "text_color",
    "logo", "font", "templates",
)
REQUIRED_TEMPLATE_KEYS = ("background", "text_zone", "photo_zone", "logo_zone")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class ConfigError(ValueError):
    """A specific, startup-safe configuration error."""


@dataclass(frozen=True)
class SubjectResolution:
    path: str | None
    warnings: tuple[str, ...] = ()

    @property
    def has_warning(self) -> bool:
        return bool(self.warnings)

    @property
    def warning_message(self) -> str | None:
        return " ".join(self.warnings) if self.warnings else None


@dataclass(frozen=True)
class HeadlineToken:
    text: str
    highlighted: bool
    joins_previous: bool = False


def _root_path(root: str | Path | None) -> Path:
    return Path(root or ROOT).resolve()


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _asset_path(root: Path, declared_path: str) -> Path:
    candidate = Path(declared_path)
    candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    return candidate


def _require(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Config error: {context}.{key} is required")
    return mapping[key]


def _validate_zone(value: Any, field: str, context: str, canvas_width: int, canvas_height: int) -> None:
    if not isinstance(value, list) or len(value) != 4:
        raise ConfigError(f"Config error: {context}.{field} must be a four-number [x, y, width, height] array")
    if any(isinstance(number, bool) or not isinstance(number, (int, float)) for number in value):
        raise ConfigError(f"Config error: {context}.{field} must contain only numbers")
    x, y, width, height = value
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > canvas_width or y + height > canvas_height:
        raise ConfigError(
            f"Config error: {context}.{field} must stay within the {canvas_width}x{canvas_height} canvas"
        )


def validate_config(config: dict[str, Any], root: str | Path = ROOT) -> list[str]:
    """Validate hard requirements and return non-fatal asset-library warnings."""
    base = _root_path(root)
    canvas = _require(config, "canvas", "root")
    if not isinstance(canvas, dict):
        raise ConfigError("Config error: root.canvas must be an object")
    width = _require(canvas, "width", "canvas")
    height = _require(canvas, "height", "canvas")
    if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ConfigError("Config error: canvas.width and canvas.height must be positive integers")

    rembg_model = _require(config, "rembg_model", "root")
    if not isinstance(rembg_model, str) or not rembg_model.strip():
        raise ConfigError("Config error: root.rembg_model must be a non-empty model name")

    domains = _require(config, "domains", "root")
    if not isinstance(domains, dict) or not domains:
        raise ConfigError("Config error: root.domains must be a non-empty object")

    for domain_name, domain in domains.items():
        domain_context = f"domains.{domain_name}"
        if not isinstance(domain, dict):
            raise ConfigError(f"Config error: {domain_context} must be an object")
        for key in REQUIRED_DOMAIN_KEYS:
            _require(domain, key, domain_context)
        for color_key in ("brand_color", "brand_color_dark", "highlight_color", "text_color"):
            if not isinstance(domain[color_key], str) or not COLOR_PATTERN.fullmatch(domain[color_key]):
                raise ConfigError(f"Config error: {domain_context}.{color_key} must be a #RRGGBB color")
        for file_key in ("logo", "font"):
            file_path = _asset_path(base, str(domain[file_key]))
            if not _is_within(file_path, base) or not file_path.is_file():
                raise ConfigError(f"Config error: {domain_context}.{file_key} file is missing: {domain[file_key]}")
        templates = domain["templates"]
        if not isinstance(templates, dict) or not templates:
            raise ConfigError(f"Config error: {domain_context}.templates must be a non-empty object")
        for template_name, template in templates.items():
            context = f"{domain_context}.templates.{template_name}"
            if not isinstance(template, dict):
                raise ConfigError(f"Config error: {context} must be an object")
            for key in REQUIRED_TEMPLATE_KEYS:
                _require(template, key, context)
            background = _asset_path(base, str(template["background"]))
            if not _is_within(background, base) or not background.is_file():
                raise ConfigError(f"Config error: {context}.background file is missing: {template['background']}")
            for zone_key in ("text_zone", "photo_zone", "logo_zone"):
                _validate_zone(template[zone_key], zone_key, context, width, height)
            if "subtitle_zone" in template:
                _validate_zone(template["subtitle_zone"], "subtitle_zone", context, width, height)

    warnings: list[str] = []
    cutouts_root = (base / "cutouts").resolve()
    category_map = _require(config, "category_to_photo_folder", "root")
    if not isinstance(category_map, dict):
        raise ConfigError("Config error: root.category_to_photo_folder must be an object")
    for category, folder in category_map.items():
        if not isinstance(folder, str):
            raise ConfigError(f"Config error: category_to_photo_folder.{category} must be a path string")
        folder_path = _asset_path(base, folder)
        if not _is_within(folder_path, cutouts_root) or not folder_path.is_dir():
            warnings.append(f"Category '{category}' has no usable cutout folder: {folder}.")

    default_cutout = config.get("default_cutout")
    if default_cutout is not None:
        if not isinstance(default_cutout, str):
            raise ConfigError("Config error: root.default_cutout must be a path string")
        default_path = _asset_path(base, default_cutout)
        if not _is_within(default_path, cutouts_root) or not default_path.is_file():
            warnings.append(f"Default cutout is unavailable: {default_cutout}.")
    return warnings


def load_config(path: str | Path = CONFIG_PATH, root: str | Path = ROOT) -> tuple[dict[str, Any], list[str]]:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            config = json.load(handle)
    except json.JSONDecodeError as error:
        raise ConfigError(f"Config error: invalid JSON in {path}: {error.msg}") from error
    warnings = validate_config(config, root)
    for warning in warnings:
        print(f"Fmaker config warning: {warning}")
    return config, warnings


CFG, CONFIG_WARNINGS = load_config()


def hx(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))


def load_font(path: str, size: int, root: str | Path = ROOT) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_asset_path(_root_path(root), path), size)


def _pick_index(seed_key: str, count: int) -> int:
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count


def pick_photo(folder: str | Path, seed_key: str) -> str | None:
    """Choose a stable category cutout for a repeatable post preview."""
    files = sorted(Path(folder).glob("*.png"))
    if not files:
        return None
    return str(files[_pick_index(seed_key, len(files))])


def _configured_default_cutout(config: dict[str, Any], root: Path) -> str | None:
    value = config.get("default_cutout")
    if not value:
        return None
    candidate = _asset_path(root, value)
    cutouts_root = (root / "cutouts").resolve()
    if _is_within(candidate, cutouts_root) and candidate.suffix.lower() == ".png" and candidate.is_file():
        return str(candidate)
    return None


def resolve_subject_photo(
    domain: str,
    category: str,
    headline: str,
    photo: str | None = None,
    shuffle: str | int | None = None,
    config: dict[str, Any] | None = None,
    root: str | Path = ROOT,
) -> SubjectResolution:
    """Resolve an approved cutout and describe every fallback to the caller."""
    selected_config = config or CFG
    base = _root_path(root)
    cutouts_root = (base / "cutouts").resolve()
    warnings: list[str] = []

    if photo:
        candidate = _asset_path(base, str(photo))
        if not _is_within(candidate, cutouts_root) or candidate.suffix.lower() != ".png":
            raise ValueError("Explicit photo must be a PNG inside the cutouts library")
        if candidate.is_file():
            return SubjectResolution(str(candidate))
        warnings.append(f"Requested photo '{photo}' was not found; selecting a fallback subject.")

    folder_name = selected_config.get("category_to_photo_folder", {}).get(category)
    folder = _asset_path(base, folder_name) if isinstance(folder_name, str) else None
    if folder and _is_within(folder, cutouts_root) and folder.is_dir():
        seed_key = "\x1f".join((domain, category, headline, str(shuffle or "")))
        resolved = pick_photo(folder, seed_key)
        if resolved:
            return SubjectResolution(resolved, tuple(warnings))

    warnings.append(f"No photo found for category '{category}'; using the default cutout when available.")
    default = _configured_default_cutout(selected_config, base)
    if default:
        return SubjectResolution(default, tuple(warnings))

    warnings.append("No default cutout is available; rendering without a subject.")
    return SubjectResolution(None, tuple(warnings))


def place_cutout(canvas: Image.Image, photo_path: str | None, zone: list[int], anchor: str) -> None:
    """Paste a transparent cutout into the photo zone, keeping aspect ratio."""
    if not photo_path:
        return
    x, y, width, height = zone
    image = Image.open(photo_path).convert("RGBA")
    scale = min(width / image.width, height / image.height)
    new_width, new_height = int(image.width * scale), int(image.height * scale)
    image = image.resize((new_width, new_height), Image.LANCZOS)
    position_x = x + (width - new_width) // 2
    position_y = y + (height - new_height) if anchor == "bottom" else y + (height - new_height) // 2
    canvas.alpha_composite(image, (position_x, position_y))


def _normalise_token(value: str) -> str:
    return value.lower().strip(string.punctuation)


def headline_tokens(title: str, highlight: str) -> list[HeadlineToken]:
    """Mark only exact, contiguous phrase matches in a whitespace-tokenized title."""
    words = title.split()
    phrase = [_normalise_token(word) for word in highlight.split() if _normalise_token(word)]
    marked = [False] * len(words)
    if phrase:
        normalised_words = [_normalise_token(word) for word in words]
        phrase_length = len(phrase)
        for start in range(len(words) - phrase_length + 1):
            if normalised_words[start:start + phrase_length] == phrase:
                for index in range(start, start + phrase_length):
                    marked[index] = True
    return [HeadlineToken(word, marked[index]) for index, word in enumerate(words)]


def _hard_break_token(draw: ImageDraw.ImageDraw, token: HeadlineToken, font: ImageFont.FreeTypeFont, max_width: int) -> list[HeadlineToken]:
    if draw.textlength(token.text, font=font) <= max_width:
        return [token]
    pieces: list[HeadlineToken] = []
    current = ""
    for character in token.text:
        candidate = current + character
        if current and draw.textlength(candidate, font=font) > max_width:
            pieces.append(HeadlineToken(current, token.highlighted, token.joins_previous if not pieces else True))
            current = character
        else:
            current = candidate
    if current:
        pieces.append(HeadlineToken(current, token.highlighted, token.joins_previous if not pieces else True))
    return pieces


def _wrap(draw: ImageDraw.ImageDraw, tokens: list[HeadlineToken], font: ImageFont.FreeTypeFont, max_width: int, space: int) -> list[list[HeadlineToken]]:
    lines: list[list[HeadlineToken]] = []
    current_line: list[HeadlineToken] = []
    current_width = 0.0
    for token in tokens:
        for piece in _hard_break_token(draw, token, font, max_width):
            piece_width = draw.textlength(piece.text, font=font)
            gap = space if current_line and not piece.joins_previous else 0
            if current_line and current_width + gap + piece_width > max_width:
                lines.append(current_line)
                current_line, current_width, gap = [], 0.0, 0
            current_line.append(piece)
            current_width += gap + piece_width
    if current_line:
        lines.append(current_line)
    return lines


def _line_width(draw: ImageDraw.ImageDraw, line: list[HeadlineToken], font: ImageFont.FreeTypeFont, space: int) -> float:
    return sum(draw.textlength(token.text, font=font) for token in line) + sum(
        space for index, token in enumerate(line) if index and not token.joins_previous
    )


def _clip_lines_to_zone(
    draw: ImageDraw.ImageDraw,
    lines: list[list[HeadlineToken]],
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
    space: int,
) -> list[list[HeadlineToken]]:
    """Keep pathological input inside the configured text zone."""
    if len(lines) <= max_lines:
        return lines
    clipped = [line[:] for line in lines[:max_lines]]
    ellipsis = HeadlineToken("…", False)
    final_line = clipped[-1]
    while final_line and _line_width(draw, final_line + [ellipsis], font, space) > max_width:
        final_line.pop()
    clipped[-1] = final_line + [ellipsis]
    return clipped


def draw_headline(
    canvas: Image.Image,
    title: str,
    highlight: str,
    zone: list[int],
    font_path: str,
    text_color: str,
    highlight_color: str,
    highlight_text_color: str,
    root: str | Path = ROOT,
    uppercase: bool = True,
) -> None:
    x, y, width, height = zone
    display_title = title.upper() if uppercase else title
    draw = ImageDraw.Draw(canvas)
    tokens = headline_tokens(display_title, highlight)
    for size in range(72, 26, -3):
        font = load_font(font_path, size, root)
        space = int(size * 0.30)
        lines = _wrap(draw, tokens, font, width, space)
        line_height = int(size * 1.22)
        if len(lines) * line_height <= height:
            break
    max_lines = max(1, height // line_height)
    lines = _clip_lines_to_zone(draw, lines, font, width, max_lines, space)
    top = y + (height - len(lines) * line_height) // 2
    padding = int(size * 0.16)
    for line in lines:
        left = x
        for index, token in enumerate(line):
            if index and not token.joins_previous:
                left += space
            token_width = draw.textlength(token.text, font=font)
            if token.highlighted:
                box = [left - padding, top - int(padding * 0.3), left + token_width + padding, top + line_height - int(padding * 0.5)]
                draw.rounded_rectangle(box, radius=6, fill=hx(highlight_color))
                draw.text((left, top), token.text, font=font, fill=hx(highlight_text_color))
            else:
                draw.text((left + 2, top + 2), token.text, font=font, fill=(0, 0, 0, 120))
                draw.text((left, top), token.text, font=font, fill=hx(text_color))
            left += token_width
        top += line_height


def draw_subtitle(canvas: Image.Image, subtitle: str, zone: list[int] | None, font_path: str, text_color: str, root: str | Path = ROOT) -> None:
    if not subtitle or not zone:
        return
    x, y, width, height = zone
    draw = ImageDraw.Draw(canvas)
    subtitle = subtitle.upper()
    for size in range(28, 13, -1):
        font = load_font(font_path, size, root)
        if draw.textlength(subtitle, font=font) <= width:
            break
    top = y + (height - size) // 2
    draw.text((x + 1, top + 1), subtitle, font=font, fill=(0, 0, 0, 120))
    draw.text((x, top), subtitle, font=font, fill=hx(text_color))


def _domain_template(domain: str, template: str, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if domain not in config["domains"]:
        raise ValueError(f"Unknown domain: {domain}")
    selected_domain = config["domains"][domain]
    if template not in selected_domain["templates"]:
        raise ValueError(f"Unknown template '{template}' for domain '{domain}'")
    return selected_domain, selected_domain["templates"][template]


def render(
    domain: str,
    template: str,
    category: str,
    title: str,
    highlight: str = "",
    subtitle: str = "",
    photo: str | None = None,
    shuffle: str | int | None = None,
    config: dict[str, Any] | None = None,
    root: str | Path = ROOT,
) -> tuple[Image.Image, SubjectResolution]:
    """Render a banner in memory and return the resolved-subject metadata."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("A headline is required")
    selected_config = config or CFG
    base = _root_path(root)
    selected_domain, selected_template = _domain_template(domain, template, selected_config)
    canvas_width, canvas_height = selected_config["canvas"]["width"], selected_config["canvas"]["height"]
    background = Image.open(_asset_path(base, selected_template["background"])).convert("RGBA")
    canvas = background.resize((canvas_width, canvas_height))

    logo = Image.open(_asset_path(base, selected_domain["logo"])).convert("RGBA")
    logo_x, logo_y, logo_width, logo_height = selected_template["logo_zone"]
    scale = min(logo_width / logo.width, logo_height / logo.height)
    logo = logo.resize((int(logo.width * scale), int(logo.height * scale)), Image.LANCZOS)
    canvas.alpha_composite(logo, (logo_x, logo_y))

    subject = resolve_subject_photo(domain, category, title, photo, shuffle, selected_config, base)
    place_cutout(canvas, subject.path, selected_template["photo_zone"], selected_template.get("photo_anchor", "bottom"))
    draw_headline(
        canvas, title.strip(), highlight, selected_template["text_zone"], selected_domain["font"],
        selected_domain["text_color"], selected_domain["highlight_color"], selected_domain["brand_color_dark"], base,
    )
    draw_subtitle(canvas, subtitle, selected_template.get("subtitle_zone"), selected_domain["font"], selected_domain["text_color"], base)
    return canvas, subject


def generate(
    domain: str,
    template: str,
    category: str,
    title: str,
    highlight: str = "",
    subtitle: str = "",
    out: str = "output/out.webp",
    photo: str | None = None,
    shuffle: str | int | None = None,
    config: dict[str, Any] | None = None,
    root: str | Path = ROOT,
) -> tuple[str, str, SubjectResolution]:
    selected_config = config or CFG
    base = _root_path(root)
    canvas, subject = render(domain, template, category, title, highlight, subtitle, photo, shuffle, selected_config, base)
    out_path = _asset_path(base, out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, selected_config["canvas"]["output_format"].upper(), quality=selected_config["canvas"]["output_quality"])
    png_path = out_path.with_suffix(".png")
    canvas.convert("RGB").save(png_path)
    return str(out_path), str(png_path), subject


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--template", default="news")
    parser.add_argument("--category", default="news")
    parser.add_argument("--title", required=True)
    parser.add_argument("--highlight", default="")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--photo", default=None)
    parser.add_argument("--shuffle", default=None)
    parser.add_argument("--out", default="output/out.webp")
    arguments = parser.parse_args()
    webp, png, subject = generate(
        arguments.domain, arguments.template, arguments.category, arguments.title,
        arguments.highlight, arguments.subtitle, arguments.out, arguments.photo, arguments.shuffle,
    )
    print("saved:", webp, "and", png)
    if subject.has_warning:
        print("warning:", subject.warning_message)
