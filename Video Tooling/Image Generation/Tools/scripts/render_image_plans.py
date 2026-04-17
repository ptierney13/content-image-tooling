import hashlib
import colorsys
import json
import math
import re
import shutil
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


RESAMPLING = Image.Resampling if hasattr(Image, "Resampling") else Image

RED = (255, 46, 33, 255)
GREEN = (100, 255, 48, 255)
SHADOW = (0, 0, 0, 135)
SLIDE_BG = (18, 18, 24, 255)
SLIDE_PANEL = (21, 22, 30, 228)
SLIDE_TEXT = (248, 248, 248, 255)
SLIDE_ACCENT = (244, 191, 82, 255)
SLIDE_LINE = (255, 229, 167, 55)
SLIDE_SUBTLE = (255, 255, 255, 18)
TITLE_SHADOW = (0, 0, 0, 110)

DEFAULT_CANVAS_SIZE = (1536, 1024)
DECKLIST_CANVAS_SIZE = (2560, 1440)
SIDEBOARD_PLAN_TYPES = {"sideboard"}
SLIDE_PLAN_TYPES = {"informative", "follow_up", "feature"}
DECKLIST_PLAN_TYPES = {"decklist"}


def _usage(script_name: str) -> int:
    print(f"Usage: python {script_name} <plans.json> [plan]")
    print("Plan types: sideboard (default), decklist, informative, follow_up, feature")
    return 1


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ensure_imports(deck_dir: Path, config: dict) -> None:
    for item in config.get("imports", []):
        source = Path(item["source"])
        destination = deck_dir / item["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)


def _resolve_size(raw: list[int] | tuple[int, int] | None) -> tuple[int, int]:
    if raw is None:
        return DEFAULT_CANVAS_SIZE
    if len(raw) != 2:
        raise ValueError(f"Expected a [width, height] size pair, received: {raw}")
    return int(raw[0]), int(raw[1])


def _resolve_deck_path(deck_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else deck_dir / path


def _is_url(value: str | None) -> bool:
    return bool(value) and value.startswith(("http://", "https://"))


def _slug(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


def _filename_slug(text: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "asset"


def _strip_known_card_suffixes(stem: str) -> str:
    cleaned = stem
    for suffix in ("-riftbound-card", "-card", "-render", "-full", "-official"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned


def _first_value(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _normalize_color(value, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return fallback


def _resolve_slide_title(plan: dict, default_title: str) -> str:
    if "title" in plan:
        return str(plan.get("title") or "")
    return default_title


def _scale_box(box: list[float], scale_x: float, scale_y: float) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    return left * scale_x, top * scale_y, right * scale_x, bottom * scale_y


def _shift_box(box: tuple[float, float, float, float], delta_x: float) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    return left + delta_x, top, right + delta_x, bottom


def _stroke(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], fill: tuple[int, int, int, int], width: int) -> None:
    rounded = [(round(x), round(y)) for x, y in points]
    draw.line(rounded, fill=fill, width=width, joint="curve")
    radius = max(1, width // 2)
    for x, y in (rounded[0], rounded[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _paint_lines(overlay: Image.Image, points: list[tuple[float, float]], width: int, color: tuple[int, int, int, int]) -> None:
    shadow = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    _stroke(shadow_draw, points, SHADOW, width + 10)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=6))
    overlay.alpha_composite(shadow)

    overlay_draw = ImageDraw.Draw(overlay)
    _stroke(overlay_draw, points, color, width)


def _draw_x(overlay: Image.Image, box: tuple[float, float, float, float]) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    stroke = max(20, round(min(width, height) * 0.17))
    margin_x = width * 0.26
    margin_y = height * 0.16
    first = [(left + margin_x, top + margin_y), (right - margin_x, bottom - margin_y)]
    second = [(right - margin_x, top + margin_y), (left + margin_x, bottom - margin_y)]
    _paint_lines(overlay, first, stroke, RED)
    _paint_lines(overlay, second, stroke, RED)


def _draw_check(overlay: Image.Image, box: tuple[float, float, float, float]) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    stroke = max(20, round(min(width, height) * 0.16))
    points = [
        (left + width * 0.18, top + height * 0.60),
        (left + width * 0.40, top + height * 0.84),
        (left + width * 0.79, top + height * 0.23),
    ]
    _paint_lines(overlay, points, stroke, GREEN)


def _draw_minus_one(overlay: Image.Image, box: tuple[float, float, float, float]) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    stroke = max(15, round(min(width, height) * 0.11))
    minus = [(left + width * 0.22, top + height * 0.47), (left + width * 0.45, top + height * 0.47)]
    body = [(left + width * 0.66, top + height * 0.20), (left + width * 0.66, top + height * 0.72)]
    _paint_lines(overlay, minus, stroke, RED)
    _paint_lines(overlay, body, stroke, RED)


def _apply_mark(overlay: Image.Image, box: tuple[float, float, float, float], mark_type: str) -> None:
    if mark_type == "x":
        _draw_x(overlay, box)
        return
    if mark_type == "check":
        _draw_check(overlay, box)
        return
    if mark_type == "minus_one":
        _draw_minus_one(overlay, box)
        return
    raise ValueError(f"Unsupported mark type: {mark_type}")


def _find_copy_gap_center_x(base: Image.Image, slot_box: tuple[float, float, float, float]) -> float | None:
    left, top, right, bottom = slot_box
    width = right - left
    height = bottom - top
    search_left = round(left + width * 0.30)
    search_top = round(top + height * 0.79)
    search_right = round(left + width * 0.70)
    search_bottom = round(top + height * 0.95)

    crop = base.crop((search_left, search_top, search_right, search_bottom)).convert("L")
    bright = crop.point(lambda value: 255 if value > 205 else 0).filter(ImageFilter.MaxFilter(size=3))
    pixels = bright.load()
    crop_width, crop_height = bright.size
    lower_start = round(crop_height * 0.52)
    histogram = []
    for x in range(crop_width):
        column_total = 0
        for y in range(lower_start, crop_height):
            column_total += pixels[x, y] // 255
        histogram.append(column_total)

    active_columns = [index for index, value in enumerate(histogram) if value >= 2]
    runs: list[tuple[int, int]] = []
    if active_columns:
        start = active_columns[0]
        end = active_columns[0]
        for index in active_columns[1:]:
            if index <= end + 1:
                end = index
            else:
                runs.append((start, end))
                start = index
                end = index
        runs.append((start, end))

    for left_run, right_run in zip(runs, runs[1:]):
        left_width = left_run[1] - left_run[0] + 1
        right_width = right_run[1] - right_run[0] + 1
        gap_width = right_run[0] - left_run[1] - 1
        if not (5 <= left_width <= 12 and 5 <= right_width <= 12):
            continue
        if not (0 <= gap_width <= 3):
            continue
        if right_run[0] > round(crop_width * 0.62):
            continue
        return search_left + ((left_run[1] + right_run[0]) / 2)

    return None


def _resolve_box_for_mark(base: Image.Image, layout: dict, slot: str, scaled_box: tuple[float, float, float, float], mark_type: str) -> tuple[float, float, float, float]:
    if mark_type != "x":
        return scaled_box

    gap_center_x = _find_copy_gap_center_x(base, scaled_box)
    if gap_center_x is not None:
        slot_center_x = (scaled_box[0] + scaled_box[2]) / 2
        return _shift_box(scaled_box, gap_center_x - slot_center_x)
    return scaled_box


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
    ]
    for raw_path in candidates:
        path = Path(raw_path)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _draw_text_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, fill: tuple) -> None:
    """Draw text visually centered (both axes) within the given box."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    glyph_w, glyph_h = right - left, bottom - top
    bw, bh = box[2] - box[0], box[3] - box[1]
    dx = box[0] + (bw - glyph_w) // 2 - left
    dy = box[1] + (bh - glyph_h) // 2 - top
    draw.text((dx, dy), text, font=font, fill=fill)


def _first_alpha_character(text: str) -> str:
    for character in text.lstrip():
        if character.isalpha():
            return character
    stripped = text.lstrip()
    if stripped:
        return stripped[0]
    return "A"


def _bullet_anchor_center_y(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, line_y: int) -> int:
    _, top, _, bottom = draw.textbbox((0, 0), _first_alpha_character(text), font=font)
    return line_y + round((top + bottom) / 2)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, *, start_size: int, min_size: int, bold: bool) -> ImageFont.ImageFont:
    for size in range(start_size, min_size - 1, -2):
        font = _load_font(size, bold=bold)
        width, _ = _text_size(draw, text, font)
        if width <= max_width:
            return font
    return _load_font(min_size, bold=bold)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        width, _ = _text_size(draw, trial, font)
        if width <= max_width:
            current = trial
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    *,
    shadow_fill: tuple[int, int, int, int] = TITLE_SHADOW,
    shadow_offset: tuple[int, int] = (3, 3),
) -> None:
    x, y = position
    draw.text((x + shadow_offset[0], y + shadow_offset[1]), text, font=font, fill=shadow_fill)
    draw.text((x, y), text, font=font, fill=fill)


def _draw_bullet_icon(draw: ImageDraw.ImageDraw, center: tuple[int, int], style: str) -> None:
    x, y = center
    if style == "diamond":
        points = [(x, y - 16), (x + 16, y), (x, y + 16), (x - 16, y)]
        draw.polygon(points, outline=SLIDE_ACCENT, width=4)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=SLIDE_ACCENT)
        return
    draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=SLIDE_ACCENT)


def _cover_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=RESAMPLING.LANCZOS)


def _center_box(size: tuple[int, int], box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    target_width = box[2] - box[0]
    target_height = box[3] - box[1]
    left = box[0] + max(0, round((target_width - size[0]) / 2))
    top = box[1] + max(0, round((target_height - size[1]) / 2))
    return left, top, left + size[0], top + size[1]


def _draw_soft_shadow(canvas: Image.Image, image: Image.Image, position: tuple[int, int], *, blur_radius: int = 22, offset: tuple[int, int] = (8, 12)) -> None:
    alpha = image.getchannel("A").point(lambda value: round(value * 0.72))
    padding = max(blur_radius * 2, 24)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 170))
    shadow.putalpha(alpha)

    shadow_canvas = Image.new("RGBA", (image.width + (padding * 2), image.height + (padding * 2)), (0, 0, 0, 0))
    shadow_canvas.alpha_composite(shadow, (padding, padding))
    shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    canvas.alpha_composite(shadow_canvas, (position[0] + offset[0] - padding, position[1] + offset[1] - padding))


def _paste_image_contained(canvas: Image.Image, source_path: Path, box: tuple[int, int, int, int], *, rotation: float = 0) -> None:
    with Image.open(source_path).convert("RGBA") as source:
        contained = ImageOps.contain(source, (box[2] - box[0], box[3] - box[1]), method=RESAMPLING.LANCZOS)
        if rotation:
            contained = contained.rotate(rotation, resample=RESAMPLING.BICUBIC, expand=True)
        paste_box = _center_box(contained.size, box)
        position = (paste_box[0], paste_box[1])
        _draw_soft_shadow(canvas, contained, position)
        canvas.alpha_composite(contained, position)


def _draw_pattern_background(size: tuple[int, int], background: dict) -> Image.Image:
    background_image = Image.new("RGBA", size, SLIDE_BG)
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((round(size[0] * 0.20), round(size[1] * 0.12), round(size[0] * 0.86), round(size[1] * 0.94)), fill=(255, 255, 255, 22))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=90))
    background_image.alpha_composite(glow)

    line_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    line_draw = ImageDraw.Draw(line_layer)
    for relative_x in (0.12, 0.30, 0.48, 0.66, 0.84):
        x = round(size[0] * relative_x)
        line_draw.line((x, 0, x, size[1]), fill=SLIDE_SUBTLE, width=2)

    for relative_x in (0.22, 0.50, 0.78):
        center_x = round(size[0] * relative_x)
        center_y = round(size[1] * 0.52)
        radius = round(size[1] * 0.17)
        line_draw.polygon([(center_x, center_y - radius), (center_x + radius, center_y), (center_x, center_y + radius), (center_x - radius, center_y)], outline=SLIDE_LINE, width=5)

    line_draw.arc((round(size[0] * 0.08), round(size[1] * 0.10), round(size[0] * 0.92), round(size[1] * 0.96)), start=180, end=360, fill=SLIDE_SUBTLE, width=4)
    line_draw.arc((round(size[0] * 0.18), round(size[1] * 0.16), round(size[0] * 0.82), round(size[1] * 0.88)), start=180, end=360, fill=SLIDE_SUBTLE, width=3)
    background_image.alpha_composite(line_layer.filter(ImageFilter.GaussianBlur(radius=1)))
    background_image.alpha_composite(Image.new("RGBA", size, (0, 0, 0, background.get("vignette_alpha", 84))))
    return background_image


def _suggest_background_image(deck_dir: Path, config: dict) -> str | None:
    candidate = config.get("base_image")
    if candidate:
        return candidate
    for folder_name in ("sources", "references"):
        folder = deck_dir / folder_name
        if not folder.exists():
            continue
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            matches = sorted(folder.glob(pattern))
            if matches:
                return str(matches[0].relative_to(deck_dir))
    return None


def _prompt_for_missing_path(label: str, suggestion: str | None) -> str:
    suggestion_label = suggestion or "none available"
    if sys.stdin.isatty():
        response = input(f"{label} not specified. Suggested '{suggestion_label}'. Press Enter to accept or type a path: ").strip()
        if response:
            return response
        if suggestion:
            return suggestion
    raise ValueError(f"{label} is required. Suggested image: {suggestion_label}")


def _resolve_background_image_path(deck_dir: Path, config: dict, raw_path: str | None, *, label: str) -> Path:
    chosen_path = raw_path or _suggest_background_image(deck_dir, config)
    if not chosen_path:
        chosen_path = _prompt_for_missing_path(label, None)
    return _resolve_deck_path(deck_dir, chosen_path)


def _draw_faded_image_background(deck_dir: Path, config: dict, background: dict, size: tuple[int, int], *, label: str) -> Image.Image:
    image_path = _resolve_background_image_path(deck_dir, config, _first_value(background.get("image"), background.get("path")), label=label)
    with Image.open(image_path).convert("RGBA") as source:
        covered = _cover_image(source, size)
    covered = covered.filter(ImageFilter.GaussianBlur(radius=background.get("blur_radius", 14)))
    covered = ImageEnhance.Color(covered).enhance(background.get("saturation", 0.46))
    covered = ImageEnhance.Brightness(covered).enhance(background.get("brightness", 0.42))
    covered.alpha_composite(Image.new("RGBA", size, _normalize_color(background.get("overlay_color"), (10, 10, 16, 170))))
    if background.get("pattern_overlay", True):
        covered.alpha_composite(_draw_pattern_background(size, {"vignette_alpha": 0}))
    return covered


def _render_slide_background(deck_dir: Path, config: dict, plan: dict, size: tuple[int, int], *, follow_up: bool = False) -> Image.Image:
    background = plan.get("background", {})
    kind = background.get("kind")
    if follow_up:
        base_slide = _first_value(plan.get("base_slide"), background.get("image"), background.get("path"))
        if kind is None:
            kind = "blurred_image"
        if kind not in {"blurred_image", "faded_image"}:
            raise ValueError(f"Unsupported follow-up background kind: {kind}")
        return _draw_faded_image_background(
            deck_dir,
            config,
            {
                "image": base_slide,
                "blur_radius": background.get("blur_radius", 18),
                "brightness": background.get("brightness", 0.48),
                "saturation": background.get("saturation", 0.45),
                "overlay_color": background.get("overlay_color", (10, 10, 14, 120)),
                "pattern_overlay": background.get("pattern_overlay", False),
            },
            size,
            label="base_slide",
        )
    if kind in (None, "pattern"):
        return _draw_pattern_background(size, background)
    if kind in {"faded_image", "decklist_faded", "blurred_image"}:
        return _draw_faded_image_background(deck_dir, config, background, size, label="background.image")
    raise ValueError(f"Unsupported background kind: {kind}")


class CardAssetResolver:
    def __init__(self, deck_dir: Path, config: dict) -> None:
        self.deck_dir = deck_dir
        self.config = config
        self.card_config = config.get("card_assets", {})
        self.cache_dir = _resolve_deck_path(deck_dir, self.card_config.get("cache_dir", "_card_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._records_by_code: dict[str, dict] = {}
        self._records_by_name: dict[str, dict] = {}
        self._catalogs_loaded = False
        self._timeout = int(self.card_config.get("timeout_seconds", 20))
        self._headers = {"User-Agent": self.card_config.get("user_agent", "RiftboundSlideGenerator/1.0")}

    def resolve_card_path(self, card: dict, *, require_official: bool | None = None) -> Path:
        if require_official is None:
            require_official = bool(_first_value(self.card_config.get("require_official_assets"), self.config.get("require_official_assets"), False))

        explicit_url = self._explicit_card_url(card, require_official=require_official)
        if explicit_url:
            return self._download_to_cache(explicit_url, hint=_first_value(card.get("card_name"), card.get("name"), card.get("card_code")))

        local_path = _first_value(card.get("local_path"), card.get("path"))
        if local_path:
            return _resolve_deck_path(self.deck_dir, local_path)

        record = self._resolve_card_record(card)
        resolved_path = _first_value(record.get("local_path"), record.get("path"))
        if resolved_path:
            resolved_local_path = _resolve_deck_path(self.deck_dir, resolved_path)
            if resolved_local_path.exists():
                return resolved_local_path
            cache_candidate = self.cache_dir / Path(str(resolved_path)).name
            if cache_candidate.exists():
                return cache_candidate

        resolved_url = self._record_image_url(record, require_official=require_official)
        if resolved_url:
            return self._download_to_cache(resolved_url, hint=_first_value(record.get("name"), record.get("cardCode")))

        if resolved_path:
            return _resolve_deck_path(self.deck_dir, resolved_path)
        raise ValueError(f"Unable to resolve a Riot card image for {card}")

    def _resolve_card_record(self, card: dict) -> dict:
        self._load_catalogs()
        card_code = _first_value(card.get("card_code"), card.get("code"))
        if card_code:
            record = self._records_by_code.get(_slug(str(card_code)))
            if record:
                return record

        card_name = _first_value(card.get("card_name"), card.get("name"))
        if card_name:
            record = self._records_by_name.get(_slug(str(card_name)))
            if record:
                return record

        raise ValueError(
            "Card image resolution requires one of: explicit riot_image_url/image_url, "
            "local_path for a pre-downloaded official asset, or a card_name/card_code plus card_assets.catalogs."
        )

    def _explicit_card_url(self, card: dict, *, require_official: bool) -> str | None:
        official_url = _first_value(card.get("official_image_url"), card.get("riot_image_url"), card.get("gameAbsolutePath"))
        if official_url:
            return official_url

        fallback_url = _first_value(card.get("image_url"), card.get("render_url"))
        if fallback_url and require_official:
            raise ValueError(
                f"Card '{_first_value(card.get('card_name'), card.get('name'), card.get('card_code'), 'unknown')}' "
                "must use an official source. Use official_image_url/riot_image_url, a catalog entry with "
                "assets[].gameAbsolutePath, or a local_path to a cached official asset."
            )
        return fallback_url

    def _catalog_sources(self) -> list:
        sources = []
        sources.extend(self.config.get("card_catalogs", []))
        sources.extend(self.card_config.get("catalogs", []))
        single_catalog = self.card_config.get("catalog")
        if single_catalog:
            sources.append(single_catalog)
        return sources

    def _load_catalogs(self) -> None:
        if self._catalogs_loaded:
            return
        for source in self._catalog_sources():
            data = self._load_catalog_source(source)
            for record in self._extract_card_records(data):
                self._register_card_record(record)
        self._catalogs_loaded = True

    def _load_catalog_source(self, source):
        if isinstance(source, dict) and any(key in source for key in ("cards", "data", "cardCode", "name")):
            return source
        if isinstance(source, dict):
            source = _first_value(source.get("path"), source.get("url"))
        if not isinstance(source, str):
            raise ValueError(f"Unsupported catalog source: {source}")
        if _is_url(source):
            return json.loads(self._read_url(source).decode("utf-8"))
        return _load_json(_resolve_deck_path(self.deck_dir, source))

    def _extract_card_records(self, data) -> list[dict]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("cards"), list):
                return [item for item in data["cards"] if isinstance(item, dict)]
            if isinstance(data.get("data"), list):
                return [item for item in data["data"] if isinstance(item, dict)]
            if any(key in data for key in ("cardCode", "name")):
                return [data]
            return [value for value in data.values() if isinstance(value, dict) and any(key in value for key in ("cardCode", "name"))]
        return []

    def _register_card_record(self, record: dict) -> None:
        card_code = record.get("cardCode")
        if card_code:
            self._records_by_code.setdefault(_slug(str(card_code)), record)
        card_name = record.get("name")
        if card_name:
            self._records_by_name.setdefault(_slug(str(card_name)), record)
        aliases = record.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if alias:
                    self._records_by_name.setdefault(_slug(str(alias)), record)

    def _record_image_url(self, record: dict, *, require_official: bool) -> str | None:
        assets = record.get("assets")
        if isinstance(assets, list) and assets:
            primary_asset = assets[0]
            if isinstance(primary_asset, dict):
                return _first_value(primary_asset.get("gameAbsolutePath"), primary_asset.get("render_url"), primary_asset.get("image_url"))

        official_url = _first_value(record.get("official_image_url"), record.get("riot_image_url"), record.get("gameAbsolutePath"))
        if official_url:
            return official_url

        fallback_url = _first_value(record.get("image_url"), record.get("render_url"))
        if fallback_url and require_official:
            raise ValueError(
                f"Catalog entry '{_first_value(record.get('name'), record.get('cardCode'), 'unknown')}' does not expose an official asset URL. "
                "Use assets[].gameAbsolutePath, official_image_url/riot_image_url, or local_path/path for a cached official export."
            )
        return fallback_url

    def _download_to_cache(self, url: str, *, hint: str | None) -> Path:
        suffix = Path(urlparse(url).path).suffix or ".png"
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        slug = _filename_slug(hint or "card")
        for candidate in sorted(self.cache_dir.glob(f"{slug}-*{suffix}")):
            if candidate.exists():
                return candidate

        destination = self.cache_dir / f"{slug}-{digest}{suffix}"
        if not destination.exists():
            destination.write_bytes(self._read_url(url))
        return destination

    def _read_url(self, url: str) -> bytes:
        request = Request(url, headers=self._headers)
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return response.read()
        except HTTPError as exc:
            raise RuntimeError(f"Request failed for {url}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc


def _with_alpha(color: tuple[int, int, int, int], alpha: int) -> tuple[int, int, int, int]:
    return int(color[0]), int(color[1]), int(color[2]), int(alpha)


def _composite_blurred_ellipse(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    *,
    blur_radius: int,
) -> None:
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(box, fill=fill)
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=blur_radius)))


def _draw_panel(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    radius: int,
    outline_width: int = 2,
) -> None:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_box = (box[0], box[1] + 14, box[2], box[3] + 14)
    shadow_draw.rounded_rectangle(shadow_box, radius=radius, fill=(0, 0, 0, 146))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(radius=20)))

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=outline_width)


def _draw_chip(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    text_fill: tuple[int, int, int, int],
) -> int:
    text_width, text_height = _text_size(draw, text, font)
    pad_x = 20
    pad_y = 11
    box = (x, y, x + text_width + (pad_x * 2), y + text_height + (pad_y * 2))
    radius = round((box[3] - box[1]) / 2)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)
    draw.text((box[0] + pad_x, box[1] + pad_y - 1), text, font=font, fill=text_fill)
    return box[2] + 14


def _draw_section_heading(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    max_x: int,
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
) -> int:
    label = text.upper()
    text_width, text_height = _text_size(draw, label, font)
    draw.text((x, y), label, font=font, fill=fill)
    line_y = y + round(text_height / 2) + 2
    if (x + text_width + 18) < max_x:
        draw.line((x + text_width + 18, line_y, max_x, line_y), fill=_with_alpha(fill, 90), width=2)
    return y + text_height


def _grid_boxes(
    count: int,
    region: tuple[int, int, int, int],
    *,
    aspect_ratio: float,
    gap_x: int,
    gap_y: int,
    max_columns: int,
    align_x: str = "center",
    align_y: str = "center",
) -> list[tuple[int, int, int, int]]:
    if count <= 0:
        return []

    region_width = region[2] - region[0]
    region_height = region[3] - region[1]
    best_layout: tuple[int, int, float, float] | None = None
    best_score = -1.0

    for columns in range(1, min(max_columns, count) + 1):
        rows = math.ceil(count / columns)
        available_width = region_width - (gap_x * (columns - 1))
        available_height = region_height - (gap_y * (rows - 1))
        if available_width <= 0 or available_height <= 0:
            continue

        cell_width = available_width / columns
        cell_height = available_height / rows
        card_width = min(cell_width, cell_height * aspect_ratio)
        card_height = card_width / aspect_ratio
        score = card_width * card_height
        if best_layout is None or score > best_score:
            best_layout = (columns, rows, card_width, card_height)
            best_score = score

    if best_layout is None:
        raise ValueError(f"Unable to place {count} cards inside region {region}.")

    columns, rows, card_width, card_height = best_layout
    grid_width = (columns * card_width) + ((columns - 1) * gap_x)
    grid_height = (rows * card_height) + ((rows - 1) * gap_y)
    if align_x == "left":
        start_x = region[0]
    elif align_x == "right":
        start_x = region[2] - round(grid_width)
    else:
        start_x = region[0] + round((region_width - grid_width) / 2)

    if align_y == "top":
        start_y = region[1]
    elif align_y == "upper_center":
        start_y = region[1] + round((region_height - grid_height) * 0.25)
    elif align_y == "bottom":
        start_y = region[3] - round(grid_height)
    else:
        start_y = region[1] + round((region_height - grid_height) / 2)

    boxes: list[tuple[int, int, int, int]] = []
    for index in range(count):
        row = index // columns
        column = index % columns
        left = round(start_x + column * (card_width + gap_x))
        top = round(start_y + row * (card_height + gap_y))
        boxes.append((left, top, round(left + card_width), round(top + card_height)))
    return boxes


def _normalize_decklist_section(label: str) -> str:
    section = _slug(label)
    aliases = {
        "legend": "legend",
        "legends": "legend",
        "champion": "champion",
        "champions": "champion",
        "maindeck": "maindeck",
        "main": "maindeck",
        "mainboard": "maindeck",
        "battlefield": "battlefields",
        "battlefields": "battlefields",
        "rune": "runes",
        "runes": "runes",
        "sideboard": "sideboard",
    }
    return aliases.get(section, section)


def _parse_decklist_text(raw_text: str) -> dict:
    sections: list[dict] = []
    by_key: dict[str, dict] = {}
    current_section: dict | None = None

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line.endswith(":"):
            label = line[:-1].strip()
            if not label:
                raise ValueError(f"Decklist line {line_number} contains an empty section heading.")
            key = _normalize_decklist_section(label)
            current_section = by_key.get(key)
            if current_section is None:
                current_section = {"label": label, "key": key, "entries": []}
                sections.append(current_section)
                by_key[key] = current_section
            continue

        if current_section is None:
            raise ValueError(f"Decklist line {line_number} appears before any section heading: {raw_line!r}")

        match = re.match(r"^(?P<count>\d+)\s+(?P<name>[^|]+?)\s*(?:\|\s*(?P<label>.+\S))?$", line)
        if not match:
            raise ValueError(f"Unable to parse decklist line {line_number}: {raw_line!r}")

        entry: dict = {"count": int(match.group("count")), "card_name": match.group("name")}
        if match.group("label"):
            entry["label"] = match.group("label")
        current_section["entries"].append(entry)

    if not sections:
        raise ValueError("Decklist text did not contain any sections.")

    return {"sections": sections, "by_key": by_key}


def _resolve_decklist_text(deck_dir: Path, config: dict, plan: dict) -> str:
    inline_text = _first_value(plan.get("decklist_text"), plan.get("decklist"), config.get("decklist_text"), config.get("decklist"))
    if inline_text:
        return str(inline_text)

    decklist_path = _first_value(plan.get("decklist_path"), plan.get("decklist_file"), config.get("decklist_path"), config.get("decklist_file"))
    if not decklist_path:
        raise ValueError("Decklist plans require decklist_text/decklist or decklist_path/decklist_file.")
    return _resolve_deck_path(deck_dir, str(decklist_path)).read_text(encoding="utf-8-sig")


def _section_entries(deck_data: dict, key: str) -> list[dict]:
    section = deck_data["by_key"].get(key)
    if not section:
        return []
    return list(section["entries"])


def _section_total(entries: list[dict]) -> int:
    return sum(int(entry["count"]) for entry in entries)


def _resolve_card_overrides(config: dict, plan: dict) -> dict:
    overrides: dict = {}
    for candidate in (config.get("card_overrides"), plan.get("card_overrides")):
        if isinstance(candidate, dict):
            overrides.update(candidate)
    return overrides


def _decklist_entry_card(entry: dict, overrides: dict) -> dict:
    override = overrides.get(entry["card_name"])
    if not isinstance(override, dict):
        override = overrides.get(_slug(entry["card_name"]))
    if not isinstance(override, dict):
        override = {}

    resolved = dict(override)
    resolved.setdefault("card_name", entry["card_name"])
    resolved["count"] = entry["count"]
    return resolved


def _draw_decklist_background(size: tuple[int, int], background: dict) -> Image.Image:
    base_color = _normalize_color(background.get("base_color"), (13, 16, 23, 255))
    accent_color = _normalize_color(background.get("accent_color"), (214, 178, 102, 255))
    secondary_color = _normalize_color(background.get("secondary_accent"), (82, 122, 176, 255))

    background_image = Image.new("RGBA", size, base_color)
    _composite_blurred_ellipse(
        background_image,
        (round(size[0] * -0.08), round(size[1] * 0.02), round(size[0] * 0.36), round(size[1] * 0.48)),
        _with_alpha(accent_color, 42),
        blur_radius=130,
    )
    _composite_blurred_ellipse(
        background_image,
        (round(size[0] * 0.60), round(size[1] * 0.10), round(size[0] * 1.08), round(size[1] * 0.90)),
        _with_alpha(secondary_color, 40),
        blur_radius=170,
    )

    pattern_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    pattern_draw = ImageDraw.Draw(pattern_layer)
    stripe_spacing = max(70, round(size[0] * 0.038))
    stripe_drop = round(size[1] * 0.84)
    for offset in range(-size[1], size[0] + stripe_spacing, stripe_spacing):
        pattern_draw.line((offset, 0, offset + stripe_drop, size[1]), fill=(255, 255, 255, 20), width=2)

    accent_spacing = stripe_spacing * 2
    for offset in range(-round(size[1] * 0.40), size[0], accent_spacing):
        pattern_draw.line(
            (offset, round(size[1] * 0.18), offset + round(size[1] * 0.50), round(size[1] * 0.68)),
            fill=_with_alpha(accent_color, 30),
            width=4,
        )

    dot_spacing_x = max(56, round(size[0] * 0.028))
    dot_spacing_y = max(56, round(size[1] * 0.040))
    dot_radius = max(2, round(size[0] * 0.0014))
    for x in range(round(size[0] * 0.05), round(size[0] * 0.30), dot_spacing_x):
        for y in range(round(size[1] * 0.18), round(size[1] * 0.90), dot_spacing_y):
            pattern_draw.ellipse((x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius), fill=(255, 255, 255, 22))

    for relative_y in (0.18, 0.52, 0.84):
        y = round(size[1] * relative_y)
        pattern_draw.line((round(size[0] * 0.04), y, round(size[0] * 0.96), y), fill=(255, 255, 255, 12), width=1)

    background_image.alpha_composite(pattern_layer.filter(ImageFilter.GaussianBlur(radius=1)))
    background_image.alpha_composite(Image.new("RGBA", size, (0, 0, 0, int(background.get("vignette_alpha", 38)))))
    return background_image


def _draw_card_badge(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    count: int,
    *,
    font: ImageFont.ImageFont,
    accent_color: tuple[int, int, int, int],
    position: str = "inside_bottom",
    offset: int = 10,
) -> None:
    if count <= 1:
        return
    text = f"{int(count)}x"
    text_width, text_height = _text_size(draw, text, font)
    pad_x = 18
    pad_y = 8
    badge_w = text_width + (pad_x * 2)
    badge_h = text_height + (pad_y * 2)
    # Center badge along the bottom edge of the card
    badge_x = (box[0] + box[2]) // 2 - badge_w // 2
    if position == "inside_bottom":
        badge_y = box[3] - badge_h - offset
    elif position == "outside_bottom":
        badge_y = box[3] - offset
    else:
        raise ValueError(f"Unsupported badge position: {position}")
    badge_box = (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h)
    radius = round(badge_h / 2)
    draw.rounded_rectangle(badge_box, radius=radius, fill=(10, 12, 18, 232), outline=_with_alpha(accent_color, 150), width=2)
    _draw_text_centered(draw, badge_box, text, font, SLIDE_TEXT)


def _draw_card_tile(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    source_path: Path,
    box: tuple[int, int, int, int],
    *,
    count: int,
    badge_font: ImageFont.ImageFont,
    accent_color: tuple[int, int, int, int],
) -> None:
    _paste_image_contained(canvas, source_path, box)
    _draw_card_badge(draw, box, count, font=badge_font, accent_color=accent_color)


def _draw_card_group(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    resolver: CardAssetResolver,
    entries: list[dict],
    overrides: dict,
    region: tuple[int, int, int, int],
    *,
    aspect_ratio: float,
    gap_x: int,
    gap_y: int,
    max_columns: int,
    badge_font: ImageFont.ImageFont,
    accent_color: tuple[int, int, int, int],
    align_x: str = "center",
    align_y: str = "center",
) -> int:
    boxes = _grid_boxes(
        len(entries),
        region,
        aspect_ratio=aspect_ratio,
        gap_x=gap_x,
        gap_y=gap_y,
        max_columns=max_columns,
        align_x=align_x,
        align_y=align_y,
    )
    for entry, box in zip(entries, boxes):
        resolved_card = _decklist_entry_card(entry, overrides)
        source_path = resolver.resolve_card_path(resolved_card, require_official=True)
        _draw_card_tile(canvas, draw, source_path, box, count=entry["count"], badge_font=badge_font, accent_color=accent_color)
    return max((b[3] for b in boxes), default=region[1])


def _draw_rune_chips(
    draw: ImageDraw.ImageDraw,
    region: tuple[int, int, int, int],
    runes: list[dict],
    *,
    font: ImageFont.ImageFont,
    accent_color: tuple[int, int, int, int],
) -> None:
    x = region[0]
    y = region[1]
    line_height = 0
    for rune in runes:
        text = f"{rune['count']} {rune['card_name']}"
        text_width, text_height = _text_size(draw, text, font)
        pad_x = 18
        pad_y = 10
        chip_width = text_width + (pad_x * 2)
        chip_height = text_height + (pad_y * 2)
        if x > region[0] and (x + chip_width) > region[2]:
            x = region[0]
            y += line_height + 12
            line_height = 0

        box = (x, y, x + chip_width, y + chip_height)
        radius = round(chip_height / 2)
        draw.rounded_rectangle(box, radius=radius, fill=(12, 15, 22, 228), outline=_with_alpha(accent_color, 118), width=2)
        draw.text((box[0] + pad_x, box[1] + pad_y - 1), text, font=font, fill=SLIDE_TEXT)

        x = box[2] + 12
        line_height = max(line_height, chip_height)


def _ensure_battlefield_labels(battlefield_entries: list[dict]) -> None:
    """Require every battlefield role to be explicitly provided by the user."""
    for entry in battlefield_entries:
        if "label" not in entry:
            if sys.stdin.isatty():
                label = input(f"Enter label for battlefield '{entry['card_name']}' (e.g. Play, Draw, Game 1): ").strip()
                entry["label"] = label or "—"
            else:
                raise ValueError(
                    "Decklist battlefield labels are required. "
                    f"Ask which role '{entry['card_name']}' has, then add '| Play', '| Draw', or '| Game 1' after the card name."
                )


def _resolve_decklist_title(config: dict, plan: dict) -> str:
    title = _first_value(plan.get("deck_name"), plan.get("title"), config.get("deck_name"), config.get("title"))
    if title:
        return str(title)
    if sys.stdin.isatty():
        prompted_title = input("Enter deck title for decklist poster: ").strip()
        if prompted_title:
            return prompted_title
    raise ValueError("Decklist poster plans require an explicit deck_name/title. Ask the user for the deck title before rendering.")


_RUNE_SYMBOL_CROP = 0.18  # fallback fraction of card's shorter side when a legend crop is unavailable
_RUNE_REFERENCE_WIDTH = 744
_RUNE_REFERENCE_HEIGHT = 1039
# Official Legend cards use a shared frame: the rune symbols live in the same
# top-left slots, so normalized crops keep future Legends aligned too.
_RUNE_SLOT_CROP_BOXES = [
    (46 / _RUNE_REFERENCE_WIDTH, 44 / _RUNE_REFERENCE_HEIGHT, 140 / _RUNE_REFERENCE_WIDTH, 138 / _RUNE_REFERENCE_HEIGHT),
    (46 / _RUNE_REFERENCE_WIDTH, 162 / _RUNE_REFERENCE_HEIGHT, 140 / _RUNE_REFERENCE_WIDTH, 256 / _RUNE_REFERENCE_HEIGHT),
]
_RUNE_KIND_BY_SLUG = {
    _slug("Body Rune"): "body",
    _slug("Calm Rune"): "calm",
    _slug("Chaos Rune"): "chaos",
    _slug("Fury Rune"): "fury",
    _slug("Mind Rune"): "mind",
    _slug("Order Rune"): "order",
}
_RUNE_COLOR_SIGNATURES = {
    # hue degrees, saturation, value. Used only to pair counts with official
    # Legend-slot crops; the displayed symbol itself is still official art.
    "body": (18.0, 0.84, 0.73),
    "calm": (78.0, 0.54, 0.36),
    "chaos": (256.0, 0.56, 0.49),
    "fury": (0.0, 0.80, 0.72),
    "mind": (206.0, 0.83, 0.49),
    "order": (48.0, 0.70, 0.72),
}


def _rune_kind_from_name(card_name: str) -> str | None:
    return _RUNE_KIND_BY_SLUG.get(_slug(card_name))


def _hue_distance(left: float, right: float) -> float:
    distance = abs(left - right) % 360
    return min(distance, 360 - distance)


def _rune_symbol_signature(symbol: Image.Image) -> tuple[float, float, float] | None:
    weighted_hues: list[tuple[float, float]] = []
    saturation_total = 0.0
    value_total = 0.0
    weight_total = 0.0
    for red, green, blue, alpha in symbol.convert("RGBA").getdata():
        if alpha < 180:
            continue
        hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        hue_degrees = hue * 360
        # Ignore white glyphs, dark texture noise, and the gold border.
        if saturation < 0.25 or value < 0.18:
            continue
        if 35 <= hue_degrees <= 65 and saturation > 0.35 and value > 0.45:
            continue
        weight = saturation * value
        weighted_hues.append((math.radians(hue_degrees), weight))
        saturation_total += saturation * weight
        value_total += value * weight
        weight_total += weight
    if weight_total <= 0:
        return None
    x = sum(math.cos(hue) * weight for hue, weight in weighted_hues)
    y = sum(math.sin(hue) * weight for hue, weight in weighted_hues)
    hue_degrees = math.degrees(math.atan2(y, x)) % 360
    return hue_degrees, saturation_total / weight_total, value_total / weight_total


def _classify_rune_symbol(symbol: Image.Image) -> str | None:
    signature = _rune_symbol_signature(symbol)
    if signature is None:
        return None
    hue, saturation, value = signature
    best_kind: str | None = None
    best_score = float("inf")
    for kind, prototype in _RUNE_COLOR_SIGNATURES.items():
        proto_hue, proto_saturation, proto_value = prototype
        score = (
            (_hue_distance(hue, proto_hue) / 180)
            + (abs(saturation - proto_saturation) * 0.35)
            + (abs(value - proto_value) * 0.18)
        )
        if score < best_score:
            best_score = score
            best_kind = kind
    return best_kind if best_score <= 0.22 else None


def _order_rune_entries_for_legend_slots(
    entries: list[dict],
    slot_symbols: list[Image.Image],
) -> tuple[list[dict], list[int]]:
    remaining = list(entries)
    ordered_entries: list[dict] = []
    ordered_slots: list[int] = []
    used_slots: set[int] = set()

    for slot_index, symbol in enumerate(slot_symbols):
        slot_kind = _classify_rune_symbol(symbol)
        match_index = None
        if slot_kind:
            for entry_index, entry in enumerate(remaining):
                if _rune_kind_from_name(entry["card_name"]) == slot_kind:
                    match_index = entry_index
                    break
        if match_index is None:
            continue
        ordered_entries.append(remaining.pop(match_index))
        ordered_slots.append(slot_index)
        used_slots.add(slot_index)

    fallback_slots = [index for index in range(len(slot_symbols)) if index not in used_slots]
    fallback_slots.extend(range(len(slot_symbols), len(entries)))
    for entry in remaining:
        ordered_entries.append(entry)
        ordered_slots.append(fallback_slots.pop(0) if fallback_slots else 0)

    return ordered_entries, ordered_slots


def _draw_rune_icons(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    resolver: CardAssetResolver,
    entries: list[dict],
    overrides: dict,
    *,
    icon_size: int,
    gap: int,
    x: int,
    y: int,
    count_font: ImageFont.ImageFont,
    accent_color: tuple[int, int, int, int],
    legend_path: "str | Path | None" = None,
    direction: str = "horizontal",
    center_y: int | None = None,
) -> tuple[int, int, int, int]:
    """Draw rune icons in a left-aligned row and return the drawn bounds.

    If legend_path is provided the symbols are cropped from the legend card's top-left corner
    (where the gold-ringed rune circles live on official legend cards).
    Otherwise falls back to cropping the top-left of each individual rune card.
    """
    n = len(entries)
    if not n:
        return (x, y, x, y)

    badge_text_height = _text_size(draw, "7x", count_font)[1]
    badge_height = badge_text_height + 16
    if direction == "horizontal":
        icon_positions = [(x + index * (icon_size + gap), y) for index in range(n)]
    elif direction == "vertical":
        stack_step = icon_size + badge_height + gap
        stack_midline = center_y if center_y is not None else y + round(((n - 1) * stack_step + icon_size) / 2)
        first_center_y = stack_midline - ((n - 1) * stack_step / 2)
        icon_positions = [
            (x, round(first_center_y + index * stack_step - icon_size / 2))
            for index in range(n)
        ]
    else:
        raise ValueError(f"Unsupported rune icon direction: {direction}")

    left = min(position[0] for position in icon_positions)
    top = min(position[1] for position in icon_positions)
    right = max(position[0] + icon_size for position in icon_positions)
    bottom = max(position[1] + icon_size + badge_height for position in icon_positions)

    if legend_path is not None:
        with Image.open(legend_path).convert("RGBA") as img:
            img_w = img.width
            img_h = img.height

            _circ_mask = Image.new("L", (icon_size, icon_size), 0)
            ImageDraw.Draw(_circ_mask).ellipse((0, 0, icon_size - 1, icon_size - 1), fill=255)

            slot_symbols: list[Image.Image] = []
            for crop_box_values in _RUNE_SLOT_CROP_BOXES:
                crop_box = tuple(round(value * dimension) for value, dimension in zip(crop_box_values, (img_w, img_h, img_w, img_h)))
                slot_symbols.append(img.crop(crop_box))
            display_entries, slot_indices = _order_rune_entries_for_legend_slots(entries, slot_symbols)

            for i, entry in enumerate(display_entries):
                icon_x, icon_y = icon_positions[i]
                slot = slot_indices[i]
                if slot < len(slot_symbols):
                    symbol = slot_symbols[slot].resize((icon_size, icon_size), RESAMPLING.LANCZOS)
                else:
                    crop_diameter = round(img_w * _RUNE_SYMBOL_CROP)
                    crop_box = (0, 0, crop_diameter, crop_diameter)
                    symbol = img.crop(crop_box).resize((icon_size, icon_size), RESAMPLING.LANCZOS)
                symbol.putalpha(_circ_mask)
                canvas.alpha_composite(symbol, (icon_x, icon_y))
                icon_box = (icon_x, icon_y, icon_x + icon_size, icon_y + icon_size)
                _draw_card_badge(
                    draw,
                    icon_box,
                    entry["count"],
                    font=count_font,
                    accent_color=accent_color,
                    position="outside_bottom",
                    offset=0,
                )
    else:
        for entry, (icon_x, icon_y) in zip(entries, icon_positions):
            resolved = _decklist_entry_card(entry, overrides)
            path = resolver.resolve_card_path(resolved, require_official=True)
            with Image.open(path).convert("RGBA") as img:
                short = min(img.width, img.height)
                crop_px = round(short * _RUNE_SYMBOL_CROP)
                symbol = img.crop((0, 0, crop_px, crop_px)).resize((icon_size, icon_size), RESAMPLING.LANCZOS)
            canvas.alpha_composite(symbol, (icon_x, icon_y))
            icon_box = (icon_x, icon_y, icon_x + icon_size, icon_y + icon_size)
            _draw_card_badge(
                draw,
                icon_box,
                entry["count"],
                font=count_font,
                accent_color=accent_color,
                position="outside_bottom",
                offset=0,
            )

    return (left, top, right, bottom)


_BATTLEFIELD_LABEL_ORDER = {"Game 1": 0, "Play": 1, "Draw": 2}


def _sort_battlefield_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda e: _BATTLEFIELD_LABEL_ORDER.get(e.get("label", ""), 99))


def _draw_battlefield_card(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    resolver: CardAssetResolver,
    entry: dict,
    overrides: dict,
    box: tuple[int, int, int, int],
    *,
    label_font: ImageFont.ImageFont,
    accent_color: tuple[int, int, int, int],
    label_gap: int,
) -> None:
    resolved = _decklist_entry_card(entry, overrides)
    path = resolver.resolve_card_path(resolved, require_official=True)
    _paste_image_contained(canvas, path, box)
    label = entry.get("label", "")
    if label:
        label_width, _ = _text_size(draw, label, label_font)
        label_x = box[0] + ((box[2] - box[0]) - label_width) // 2
        label_y = box[3] + label_gap
        draw.text((label_x + 1, label_y + 1), label, font=label_font, fill=(0, 0, 0, 160))
        draw.text((label_x, label_y), label, font=label_font, fill=_with_alpha(accent_color, 230))


def _draw_battlefields_with_labels(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    resolver: CardAssetResolver,
    entries: list[dict],
    overrides: dict,
    region: tuple[int, int, int, int],
    *,
    label_font: ImageFont.ImageFont,
    accent_color: tuple[int, int, int, int],
    card_size: "tuple[int, int] | None" = None,
) -> int:
    """Draw battlefields: Game 1 full-width on top, Play and Draw side by side below.

    If card_size=(card_w, card_h) is provided all three cards are rendered at that exact size.
    Otherwise sizes are derived from the region dimensions.
    """
    if not entries:
        return region[1]

    _, lh = _text_size(draw, "Play", label_font)
    label_gap = 5
    row_gap = 14
    col_gap = 10
    inner_w = region[2] - region[0]
    total_h = region[3] - region[1]

    game1_entries = [e for e in entries if e.get("label") == "Game 1"]
    other_entries = [e for e in entries if e.get("label") != "Game 1"]
    has_game1 = bool(game1_entries)
    has_others = bool(other_entries)
    n_rows = (1 if has_game1 else 0) + (1 if has_others else 0)

    if card_size is not None:
        bf_card_w, bf_card_h = card_size
    else:
        net_h = total_h - n_rows * (lh + label_gap) - max(0, n_rows - 1) * row_gap
        bf_card_h = max(40, net_h // max(1, n_rows))
        bf_card_w = round(bf_card_h * 1.62)

    cursor = region[1]

    def _draw_bf_card(entry: dict, box: tuple[int, int, int, int], cw: int, ch: int) -> None:
        resolved = _decklist_entry_card(entry, overrides)
        path = resolver.resolve_card_path(resolved, require_official=True)
        _paste_image_contained(canvas, path, box)
        label = entry.get("label", "")
        if label:
            tw, _ = _text_size(draw, label, label_font)
            lx_label = box[0] + (cw - tw) // 2
            ly_label = box[1] + ch + label_gap
            draw.text((lx_label + 1, ly_label + 1), label, font=label_font, fill=(0, 0, 0, 160))
            draw.text((lx_label, ly_label), label, font=label_font, fill=_with_alpha(accent_color, 230))

    # Game 1 — same card dimensions, top row
    if has_game1:
        box = (region[0], cursor, region[0] + bf_card_w, cursor + bf_card_h)
        _draw_battlefield_card(canvas, draw, resolver, game1_entries[0], overrides, box, label_font=label_font, accent_color=accent_color, label_gap=label_gap)
        cursor += bf_card_h + lh + label_gap + row_gap

    # Play + Draw — same card dimensions, side by side
    if has_others:
        ox = region[0]
        for entry in other_entries:
            box = (ox, cursor, ox + bf_card_w, cursor + bf_card_h)
            _draw_battlefield_card(canvas, draw, resolver, entry, overrides, box, label_font=label_font, accent_color=accent_color, label_gap=label_gap)
            ox += bf_card_w + col_gap
        cursor += bf_card_h + lh + label_gap

    return cursor


def _draw_decklist_plan(deck_dir: Path, config: dict, output_path: Path, matchup_name: str, plan: dict, resolver: CardAssetResolver) -> Path:
    deck_data = _parse_decklist_text(_resolve_decklist_text(deck_dir, config, plan))
    overrides = _resolve_card_overrides(config, plan)

    background = {}
    if isinstance(config.get("background"), dict):
        background.update(config["background"])
    if isinstance(plan.get("background"), dict):
        background.update(plan["background"])

    size = _resolve_size(_first_value(plan.get("canvas_size"), config.get("canvas_size"), DECKLIST_CANVAS_SIZE))
    canvas = _draw_decklist_background(size, background)
    draw = ImageDraw.Draw(canvas)

    accent_color = _normalize_color(_first_value(plan.get("accent_color"), background.get("accent_color")), (214, 178, 102, 255))

    title = _resolve_decklist_title(config, plan)
    subtitle = _first_value(plan.get("subtitle"), config.get("subtitle"))
    footer = _first_value(plan.get("footer"), config.get("footer"))

    legend_entries = _section_entries(deck_data, "legend")
    champion_entries = _section_entries(deck_data, "champion")
    main_entries = _section_entries(deck_data, "maindeck")
    battlefield_entries = _section_entries(deck_data, "battlefields")
    rune_entries = _section_entries(deck_data, "runes")
    sideboard_entries = _section_entries(deck_data, "sideboard")

    if not main_entries:
        raise ValueError("Decklist plans require a MainDeck section with at least one card entry.")

    legend_champion_entries = legend_entries + champion_entries

    margin = max(44, round(size[0] * 0.022))
    title_font = _fit_font(draw, title, size[0] - (margin * 2), start_size=max(74, round(size[0] * 0.037)), min_size=58, bold=True)
    section_font = _load_font(max(26, round(size[0] * 0.011)), bold=True)
    badge_font = _load_font(max(24, round(size[0] * 0.0105)), bold=True)
    bf_label_font = _load_font(max(22, round(size[0] * 0.009)), bold=False)

    title_y = margin - 10
    _draw_text_with_shadow(draw, (margin, title_y), title, title_font, SLIDE_TEXT)
    _, title_height = _text_size(draw, title, title_font)
    content_top = max(round(size[1] * 0.13), title_y + title_height + 36)

    gap = max(26, round(size[0] * 0.014))
    left_width = round(size[0] * 0.26)
    left_panel = (margin, content_top, margin + left_width, size[1] - margin)
    right_panel = (left_panel[2] + gap, content_top, size[0] - margin, size[1] - margin)
    left_height = left_panel[3] - left_panel[1]

    # Pre-compute right column bounds (needed by battlefield→sideboard offset logic)
    rx = right_panel[0] + 10
    rxr = right_panel[2] - 10

    # ── Left column ──────────────────────────────────────────────────────────
    lx = left_panel[0] + 10
    lxr = left_panel[2] - 10
    cursor_y = left_panel[1]

    # Legend / Champion — side by side
    if legend_champion_entries:
        if legend_entries and champion_entries:
            lc_label = "Legend / Champion"
        elif legend_entries:
            lc_label = "Legend"
        else:
            lc_label = "Champion"
        lc_region_right = min(right_panel[0] - 14, lxr + round(size[0] * 0.012))
        cursor_y = _draw_section_heading(draw, lx, cursor_y, lc_region_right, lc_label, font=section_font, fill=_with_alpha(accent_color, 230)) + 12
        lc_height = round(left_height * 0.46)
        lc_draw_offset = max(6, round(size[1] * 0.006))
        lc_region = (lx, cursor_y + lc_draw_offset, lc_region_right, cursor_y + lc_draw_offset + lc_height)
        lc_bottom = _draw_card_group(
            canvas, draw, resolver, legend_champion_entries, overrides, lc_region,
            aspect_ratio=0.74, gap_x=10, gap_y=0,
            max_columns=max(1, len(legend_champion_entries)),
            badge_font=badge_font, accent_color=accent_color, align_x="left", align_y="top",
        )
        cursor_y = (lc_bottom - lc_draw_offset) + 12

    # Battlefields / Runes — merged layout with runes in the old Game 1 slot
    sb_start_x = rx  # default: sideboard aligned with maindeck left edge
    if battlefield_entries or rune_entries:
        sorted_bf: list[dict] = []
        if battlefield_entries:
            _ensure_battlefield_labels(battlefield_entries)
            sorted_bf = _sort_battlefield_entries(battlefield_entries)

        cursor_y = _draw_section_heading(draw, lx, cursor_y, lxr, "Battlfields / Runes", font=section_font, fill=_with_alpha(accent_color, 230)) + 12

        game1_entries = [entry for entry in sorted_bf if entry.get("label") == "Game 1"]
        other_entries = [entry for entry in sorted_bf if entry.get("label") != "Game 1"]
        _, battlefield_label_height = _text_size(draw, "Play", bf_label_font)
        battlefield_label_gap = 5
        battlefield_row_gap = 14
        battlefield_row_count = (1 if (game1_entries or rune_entries) else 0) + (1 if other_entries else 0)
        battlefield_space = left_panel[3] - cursor_y
        top_row_label_space = (battlefield_label_height + battlefield_label_gap) if game1_entries else 0
        bottom_row_label_space = (battlefield_label_height + battlefield_label_gap) if other_entries else 0
        battlefield_net_height = battlefield_space - top_row_label_space - bottom_row_label_space - max(0, battlefield_row_count - 1) * battlefield_row_gap
        battlefield_card_h = max(40, battlefield_net_height // max(1, battlefield_row_count))
        battlefield_card_w = round(battlefield_card_h * 1.62)
        battlefield_col_gap = 10
        desired_rune_icon_size = max(80, round(size[0] * 0.039))
        merged_rune_icon_size = min(desired_rune_icon_size, max(56, battlefield_card_h - 12))
        rune_left_offset = max(16, round(size[0] * 0.010))
        game1_rune_gap = max(36, round(size[0] * 0.018))

        block_right = lx
        top_row_bottom = cursor_y
        top_row_x = lx + rune_left_offset

        if rune_entries:
            legend_path: Path | None = None
            if legend_entries:
                legend_card = _decklist_entry_card(legend_entries[0], overrides)
                try:
                    legend_path = resolver.resolve_card_path(legend_card, require_official=True)
                except Exception:
                    legend_path = None
            rune_box = _draw_rune_icons(
                canvas,
                draw,
                resolver,
                rune_entries,
                overrides,
                icon_size=merged_rune_icon_size,
                gap=12,
                x=top_row_x,
                y=cursor_y,
                count_font=badge_font,
                accent_color=accent_color,
                legend_path=legend_path,
                direction="vertical",
                center_y=cursor_y + round(battlefield_card_h / 2),
            )
            top_row_x = rune_box[2] + game1_rune_gap
            block_right = max(block_right, rune_box[2])
            top_row_bottom = max(top_row_bottom, rune_box[3])

        if game1_entries:
            game1_box = (top_row_x, cursor_y, top_row_x + battlefield_card_w, cursor_y + battlefield_card_h)
            _draw_battlefield_card(
                canvas,
                draw,
                resolver,
                game1_entries[0],
                overrides,
                game1_box,
                label_font=bf_label_font,
                accent_color=accent_color,
                label_gap=battlefield_label_gap,
            )
            block_right = max(block_right, game1_box[2])
            top_row_bottom = max(top_row_bottom, game1_box[3] + battlefield_label_height + battlefield_label_gap)

        cursor_y = top_row_bottom + (battlefield_row_gap if other_entries else 0)

        if other_entries:
            other_row_x = lx
            other_row_bottom = cursor_y
            for entry in other_entries:
                box = (other_row_x, cursor_y, other_row_x + battlefield_card_w, cursor_y + battlefield_card_h)
                _draw_battlefield_card(
                    canvas,
                    draw,
                    resolver,
                    entry,
                    overrides,
                    box,
                    label_font=bf_label_font,
                    accent_color=accent_color,
                    label_gap=battlefield_label_gap,
                )
                block_right = max(block_right, box[2])
                other_row_bottom = max(other_row_bottom, box[3] + battlefield_label_height + battlefield_label_gap)
                other_row_x += battlefield_card_w + battlefield_col_gap
            cursor_y = other_row_bottom

        sb_start_x = block_right + gap
        rune_entries = []
        battlefield_entries = []

    # Runes — small clipped symbols directly under legend/champion, no heading
    if False and rune_entries:
        # Use the legend card to crop the actual rune symbols from its top-left corner
        _legend_path: "Path | None" = None
        if legend_entries:
            _legend_resolved = _decklist_entry_card(legend_entries[0], overrides)
            try:
                _legend_path = resolver.resolve_card_path(_legend_resolved, require_official=True)
            except Exception:
                _legend_path = None
        cursor_y = _draw_rune_icons(
            canvas, draw, resolver, rune_entries, overrides,
            icon_size=rune_icon_size, gap=12,
            region_x=lx, region_right=lxr,
            y=cursor_y,
            count_font=rune_count_font,
            legend_path=_legend_path,
        ) + 16

    # Battlefields — Game 1 on top, Play+Draw side by side below, all same card size
    sb_start_x = max(sb_start_x, rx)  # default: sideboard aligned with maindeck left edge
    if False and battlefield_entries:
        _ensure_battlefield_labels(battlefield_entries)
        sorted_bf = _sort_battlefield_entries(battlefield_entries)
        cursor_y = _draw_section_heading(draw, lx, cursor_y, lxr, "Battlefields", font=section_font, fill=_with_alpha(accent_color, 230)) + 12

        # Pre-compute card size so Game 1 and Play+Draw are identical.
        # Available vertical space is split evenly between the two rows.
        _, _lh_bf = _text_size(draw, "Play", bf_label_font)
        _bf_label_gap = 5
        _bf_row_gap = 14
        _bf_n_rows = 2  # Game 1 row + Play+Draw row
        _bf_v_space = left_panel[3] - cursor_y
        _bf_net_h = _bf_v_space - _bf_n_rows * (_lh_bf + _bf_label_gap) - (_bf_n_rows - 1) * _bf_row_gap
        bf_card_h = max(40, _bf_net_h // 2)
        bf_card_w = round(bf_card_h * 1.62)
        # The Play+Draw row is two cards side by side — the region must be wide enough.
        bf_col_gap = 10
        bf_total_w = 2 * bf_card_w + bf_col_gap

        bf_region = (lx, cursor_y, lx + bf_total_w, left_panel[3])
        _draw_battlefields_with_labels(canvas, draw, resolver, sorted_bf, overrides, bf_region,
                                        label_font=bf_label_font, accent_color=accent_color,
                                        card_size=(bf_card_w, bf_card_h))
        # Sideboard starts to the right of the battlefield block
        sb_start_x = lx + bf_total_w + gap

    # ── Right column ──────────────────────────────────────────────────────────
    right_inner_w = rxr - rx

    # Pre-compute a shared card size so main deck and sideboard cards are identical.
    # Card width is driven by max_cols_main and available horizontal space.
    # Both sections are given regions sized to exactly those card dimensions.
    max_cols_main = max(1, min(8, len(main_entries)))
    rows_main = math.ceil(len(main_entries) / max_cols_main)
    target_card_w = (right_inner_w - (max_cols_main - 1) * 18) / max_cols_main
    target_card_h = round(target_card_w / 0.74)

    main_heading_bottom = _draw_section_heading(
        draw, rx, right_panel[1] + 6, rxr, "Main Deck",
        font=section_font, fill=_with_alpha(accent_color, 230),
    )
    main_card_area_h = rows_main * target_card_h + (rows_main - 1) * 20
    main_region = (rx, main_heading_bottom + 12, rxr, main_heading_bottom + 12 + main_card_area_h)
    _draw_card_group(
        canvas, draw, resolver, main_entries, overrides, main_region,
        aspect_ratio=0.74, gap_x=18, gap_y=20, max_columns=max_cols_main,
        badge_font=badge_font, accent_color=accent_color, align_y="top",
    )

    if sideboard_entries:
        # Sideboard may be shifted right (sb_start_x > rx) to make room for battlefield cards
        sb_rx = max(sb_start_x, rx) + 10
        sb_inner_w = rxr - sb_rx
        # Determine column count so cards fit in the (possibly narrower) sideboard area
        max_cols_sb = max(1, min(max_cols_main, len(sideboard_entries)))
        # Shrink column count until cards fit horizontally at target_card_w
        while max_cols_sb > 1 and (sb_inner_w - (max_cols_sb - 1) * 18) / max_cols_sb < target_card_w * 0.7:
            max_cols_sb -= 1
        rows_sb = math.ceil(len(sideboard_entries) / max_cols_sb)
        sb_heading_bottom = _draw_section_heading(
            draw, sb_rx, main_region[3] + gap + 6, rxr, "Sideboard",
            font=section_font, fill=_with_alpha(accent_color, 230),
        )
        sb_card_area_h = rows_sb * target_card_h + (rows_sb - 1) * 20
        sb_region = (sb_rx, sb_heading_bottom + 12, rxr, sb_heading_bottom + 12 + sb_card_area_h)
        _draw_card_group(
            canvas, draw, resolver, sideboard_entries, overrides, sb_region,
            aspect_ratio=0.74, gap_x=18, gap_y=20, max_columns=max_cols_sb,
            badge_font=badge_font, accent_color=accent_color, align_x="left", align_y="top",
        )

    canvas.save(output_path)
    print(f"{matchup_name}: {output_path}")
    return output_path


def _default_output_image(plan: dict) -> str | None:
    if plan.get("type") == "decklist":
        title = _first_value(plan.get("deck_name"), plan.get("title"))
        if title:
            return f"{_filename_slug(str(title))}.png"
        return None

    if plan.get("type") != "feature":
        return None

    cards = plan.get("cards", [])
    if len(cards) != 1:
        raise ValueError("Feature slides require exactly one card to derive a default filename.")

    base_slide_path = _first_value(plan.get("base_slide"), plan.get("background", {}).get("image"), plan.get("background", {}).get("path"))
    if not base_slide_path:
        raise ValueError("Feature slides require a base_slide or background image to derive a default filename.")

    card = cards[0]
    card_name = _first_value(card.get("card_name"), card.get("name"), card.get("card_code"))
    if not card_name:
        local_path = _first_value(card.get("local_path"), card.get("path"))
        if local_path:
            card_name = _strip_known_card_suffixes(Path(str(local_path)).stem)
    if not card_name:
        raise ValueError("Feature slides need a card_name/name/card_code or local_path/path to derive the default filename.")

    source_stem = _filename_slug(Path(str(base_slide_path)).stem)
    card_stem = _filename_slug(str(card_name))
    return f"{source_stem}-featuring-{card_stem}.png"


def _resolve_output_path(deck_dir: Path, config: dict, plan: dict) -> Path:
    plan_type = plan.get("type", "sideboard")
    output_path = plan.get("output_path")
    if output_path:
        resolved = _resolve_deck_path(deck_dir, output_path)
    else:
        if plan_type in SLIDE_PLAN_TYPES:
            default_output_dir = ".."
        elif plan_type == "decklist":
            default_output_dir = ".."
        else:
            default_output_dir = ".."
        output_dir = _resolve_deck_path(deck_dir, plan.get("output_dir") or config.get("output_dir", default_output_dir))
        output_name = plan.get("output_image") or _default_output_image(plan)
        if not output_name:
            raise ValueError("Plan must include either output_path or output_image.")
        resolved = output_dir / output_name
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_card_box(card: dict, default_box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    explicit_box = card.get("box")
    if explicit_box:
        return tuple(int(value) for value in explicit_box)
    position = card.get("position")
    size = card.get("size")
    if position and size:
        return (int(position[0]), int(position[1]), int(position[0] + size[0]), int(position[1] + size[1]))
    return default_box


def _informative_card_boxes(count: int) -> list[tuple[int, int, int, int]]:
    if count == 0:
        return []
    if count == 1:
        return [(44, 196, 570, 960)]
    return [(36, 210, 448, 760), (170, 474, 582, 1014)]


def _prepare_bullet_layouts(
    draw: ImageDraw.ImageDraw,
    bullets: list,
    font: ImageFont.ImageFont,
    max_width: int,
    *,
    bullet_indent: int,
    default_style: str,
    line_spacing: int,
) -> list[dict]:
    bullet_layouts = []
    text_width = max(40, max_width - bullet_indent)
    for bullet in bullets:
        text = bullet["text"] if isinstance(bullet, dict) else str(bullet)
        style = bullet.get("style", default_style) if isinstance(bullet, dict) else default_style
        lines = _wrap_text(draw, text, font, text_width)
        line_heights = [_text_size(draw, line, font)[1] for line in lines]
        total_height = sum(line_heights) + (line_spacing * max(0, len(lines) - 1))
        bullet_layouts.append(
            {
                "style": style,
                "lines": lines,
                "line_heights": line_heights,
                "total_height": total_height,
            }
        )
    return bullet_layouts


def _resolve_bullet_spacing(current_y: int, text_bottom: int | None, bullet_layouts: list[dict], bullet_spacing: int) -> int:
    if text_bottom is not None and len(bullet_layouts) > 1:
        total_bullet_height = sum(layout["total_height"] for layout in bullet_layouts)
        available_gap = int(text_bottom) - int(current_y) - total_bullet_height
        return max(0, math.floor(available_gap / (len(bullet_layouts) - 1)))
    return bullet_spacing


def _draw_bullet_layouts(
    draw: ImageDraw.ImageDraw,
    bullet_layouts: list[dict],
    *,
    text_left: int,
    current_y: int,
    font: ImageFont.ImageFont,
    line_spacing: int,
    bullet_spacing: int,
    bullet_indent: int,
) -> int:
    for bullet_layout in bullet_layouts:
        bullet_center_y = _bullet_anchor_center_y(draw, bullet_layout["lines"][0], font, current_y)
        _draw_bullet_icon(draw, (text_left, bullet_center_y), bullet_layout["style"])
        line_y = current_y
        for line, line_height in zip(bullet_layout["lines"], bullet_layout["line_heights"]):
            _draw_text_with_shadow(draw, (text_left + bullet_indent, line_y), line, font, SLIDE_TEXT, shadow_offset=(2, 2))
            line_y += line_height + line_spacing
        current_y = line_y + bullet_spacing
    return current_y


def _draw_informative_sections(draw: ImageDraw.ImageDraw, plan: dict, size: tuple[int, int], *, text_left: int, text_right: int, current_y: int) -> None:
    sections = plan.get("sections", [])
    if not sections:
        return

    sections_top = int(plan.get("sections_top", max(current_y + 38, round(size[1] * 0.48))))
    sections_bottom = int(plan.get("sections_bottom", size[1] - 86))
    sections_left = int(plan.get("sections_left", text_left))
    sections_right = int(plan.get("sections_right", text_right))
    section_gap = int(plan.get("section_gap", 64))
    section_count = len(sections)
    if section_count < 1:
        return

    draw.line((sections_left, sections_top - 28, sections_right, sections_top - 28), fill=SLIDE_LINE, width=3)
    if section_count == 2:
        divider_x = round((sections_left + sections_right) / 2)
        draw.line((divider_x, sections_top - 2, divider_x, sections_bottom), fill=SLIDE_LINE, width=2)

    total_gap = section_gap * max(0, section_count - 1)
    column_width = (sections_right - sections_left - total_gap) / section_count
    title_start_size = int(plan.get("section_title_font_size", 46))
    title_min_size = int(plan.get("section_title_min_font_size", 34))
    body_size = int(plan.get("section_body_font_size", 34))
    line_spacing = int(plan.get("section_line_spacing", 8))
    bullet_spacing = int(plan.get("section_bullet_spacing", 22))
    bullet_indent = int(plan.get("section_bullet_indent", 38))
    bullet_style = plan.get("section_bullet_style", plan.get("bullet_style", "dot"))

    for index, section in enumerate(sections):
        column_left = round(sections_left + index * (column_width + section_gap))
        column_right = round(column_left + column_width)
        title = str(section.get("title", ""))
        title_y = sections_top
        if title:
            title_font = _fit_font(draw, title, column_right - column_left, start_size=title_start_size, min_size=title_min_size, bold=True)
            _draw_text_with_shadow(draw, (column_left, title_y), title, title_font, SLIDE_ACCENT, shadow_offset=(2, 2))
            _, title_height = _text_size(draw, title, title_font)
        else:
            title_height = 0

        underline_y = title_y + title_height + 18
        draw.line((column_left, underline_y, column_right, underline_y), fill=SLIDE_LINE, width=2)

        section_font = _load_font(int(section.get("body_font_size", body_size)), bold=False)
        section_bullets = section.get("bullets", [])
        bullet_layouts = _prepare_bullet_layouts(
            draw,
            section_bullets,
            section_font,
            column_right - column_left,
            bullet_indent=bullet_indent,
            default_style=section.get("bullet_style", bullet_style),
            line_spacing=line_spacing,
        )
        section_current_y = underline_y + 28
        resolved_spacing = _resolve_bullet_spacing(section_current_y, sections_bottom, bullet_layouts, bullet_spacing)
        _draw_bullet_layouts(
            draw,
            bullet_layouts,
            text_left=column_left,
            current_y=section_current_y,
            font=section_font,
            line_spacing=line_spacing,
            bullet_spacing=resolved_spacing,
            bullet_indent=bullet_indent,
        )


def _draw_informative_slide(deck_dir: Path, config: dict, output_path: Path, matchup_name: str, plan: dict, resolver: CardAssetResolver) -> Path:
    size = _resolve_size(_first_value(plan.get("canvas_size"), config.get("canvas_size")))
    canvas = _render_slide_background(deck_dir, config, plan, size)
    draw = ImageDraw.Draw(canvas)

    title = _resolve_slide_title(plan, matchup_name)
    cards = plan.get("cards", [])
    if len(cards) > 2:
        raise ValueError("Informative slides support zero, one, or two cards on the left.")

    if title:
        title_font = _fit_font(draw, title, size[0] - 180, start_size=84, min_size=54, bold=True)
        title_width, _ = _text_size(draw, title, title_font)
        title_x = 78 if plan.get("title_align", "center") == "left" else round((size[0] - title_width) / 2)
        _draw_text_with_shadow(draw, (title_x, 70), title, title_font, SLIDE_TEXT)

    for default_box, card in zip(_informative_card_boxes(len(cards)), cards):
        card_path = resolver.resolve_card_path(card)
        _paste_image_contained(canvas, card_path, _resolve_card_box(card, default_box), rotation=float(card.get("rotation", 0)))

    bullets = plan.get("bullets", [])
    sections = plan.get("sections", [])
    if not bullets and not sections:
        raise ValueError("Informative slides require a non-empty bullets list or sections list.")

    body_font = _load_font(plan.get("body_font_size", 46), bold=False)
    text_left = 100 if not cards else 635
    text_right = size[0] - 86
    text_width = text_right - text_left
    current_y = plan.get("text_top", 312 if cards else 238)
    line_spacing = plan.get("line_spacing", 14)
    bullet_spacing = plan.get("bullet_spacing", 34)
    bullet_indent = plan.get("bullet_indent", 46)
    bullet_style = plan.get("bullet_style", "dot")
    text_bottom = plan.get("top_bullets_bottom") if sections else plan.get("text_bottom")
    if text_bottom is None:
        text_bottom = plan.get("text_bottom")

    if bullets:
        bullet_layouts = _prepare_bullet_layouts(
            draw,
            bullets,
            body_font,
            text_width,
            bullet_indent=bullet_indent,
            default_style=bullet_style,
            line_spacing=line_spacing,
        )
        bullet_spacing = _resolve_bullet_spacing(current_y, text_bottom, bullet_layouts, bullet_spacing)
        current_y = _draw_bullet_layouts(
            draw,
            bullet_layouts,
            text_left=text_left,
            current_y=current_y,
            font=body_font,
            line_spacing=line_spacing,
            bullet_spacing=bullet_spacing,
            bullet_indent=bullet_indent,
        )

    _draw_informative_sections(draw, plan, size, text_left=text_left, text_right=text_right, current_y=current_y)

    canvas.save(output_path)
    print(f"{matchup_name}: {output_path}")
    return output_path


def _auto_follow_up_boxes(count: int, size: tuple[int, int], *, title_present: bool) -> list[tuple[int, int, int, int]]:
    if count <= 0:
        return []
    columns = count if count <= 3 else 3 if count <= 6 else 4
    rows = math.ceil(count / columns)
    top_margin = 300 if title_present else 180
    side_margin = 90
    bottom_margin = 88
    gap_x = 54
    gap_y = 46
    available_width = size[0] - (side_margin * 2) - (gap_x * (columns - 1))
    available_height = size[1] - top_margin - bottom_margin - (gap_y * (rows - 1))
    card_width = min(available_width / columns, available_height / rows * 0.75)
    card_height = card_width / 0.75
    grid_width = columns * card_width + (columns - 1) * gap_x
    start_x = round((size[0] - grid_width) / 2)
    boxes = []
    for index in range(count):
        row = index // columns
        column = index % columns
        left = round(start_x + column * (card_width + gap_x))
        top = round(top_margin + row * (card_height + gap_y))
        boxes.append((left, top, round(left + card_width), round(top + card_height)))
    return boxes


def _resolve_follow_up_boxes(plan: dict, size: tuple[int, int], *, title_present: bool, card_count: int) -> list[tuple[int, int, int, int]]:
    raw_layout = plan.get("card_layout", "grid")
    if isinstance(raw_layout, dict):
        layout_mode = raw_layout.get("mode", "grid")
        layout_config = raw_layout
    else:
        layout_mode = raw_layout or "grid"
        layout_config = {}

    if layout_mode == "grid":
        return _auto_follow_up_boxes(card_count, size, title_present=title_present)

    if layout_mode == "featured_center":
        if card_count != 1:
            raise ValueError("card_layout 'featured_center' requires exactly one card.")

        top_margin = int(layout_config.get("top_margin", 220 if title_present else 24))
        bottom_margin = int(layout_config.get("bottom_margin", 48))
        side_margin = int(layout_config.get("side_margin", 120))
        if (side_margin * 2) >= size[0] or (top_margin + bottom_margin) >= size[1]:
            raise ValueError("featured_center margins leave no room for the card.")
        return [(side_margin, top_margin, size[0] - side_margin, size[1] - bottom_margin)]

    raise ValueError(f"Unsupported follow-up card_layout mode: {layout_mode}")


def _draw_follow_up_slide(deck_dir: Path, config: dict, output_path: Path, matchup_name: str, plan: dict, resolver: CardAssetResolver) -> Path:
    base_slide_path = _first_value(plan.get("base_slide"), plan.get("background", {}).get("image"), plan.get("background", {}).get("path"))
    if not base_slide_path:
        base_slide_path = _prompt_for_missing_path("base_slide", _suggest_background_image(deck_dir, config))
    resolved_base_slide = _resolve_deck_path(deck_dir, base_slide_path)
    with Image.open(resolved_base_slide).convert("RGBA") as source:
        default_size = source.size

    size = _resolve_size(_first_value(plan.get("canvas_size"), default_size, config.get("canvas_size")))
    canvas = _render_slide_background(deck_dir, config, {**plan, "base_slide": base_slide_path}, size, follow_up=True)
    draw = ImageDraw.Draw(canvas)

    title = _resolve_slide_title(plan, matchup_name)
    if title:
        title_font = _fit_font(draw, title, size[0] - 160, start_size=86, min_size=52, bold=True)
        title_width, _ = _text_size(draw, title, title_font)
        _draw_text_with_shadow(draw, (round((size[0] - title_width) / 2), 72), title, title_font, SLIDE_TEXT)

    cards = plan.get("cards", [])
    if not cards:
        raise ValueError("Follow-up slides require a non-empty cards list.")

    for default_box, card in zip(_resolve_follow_up_boxes(plan, size, title_present=bool(title), card_count=len(cards)), cards):
        card_path = resolver.resolve_card_path(card)
        _paste_image_contained(canvas, card_path, _resolve_card_box(card, default_box), rotation=float(card.get("rotation", 0)))

    canvas.save(output_path)
    print(f"{matchup_name}: {output_path}")
    return output_path


def _draw_feature_slide(deck_dir: Path, config: dict, output_path: Path, matchup_name: str, plan: dict, resolver: CardAssetResolver) -> Path:
    feature_plan = dict(plan)
    feature_plan.setdefault("title", "")
    feature_plan.setdefault("card_layout", {"mode": "featured_center"})
    return _draw_follow_up_slide(deck_dir, config, output_path, matchup_name, feature_plan, resolver)


def _render_sideboard_plan(deck_dir: Path, config: dict, layout: dict, base_image_path: Path, matchup_name: str, plan: dict) -> Path:
    output_path = _resolve_output_path(deck_dir, config, plan)
    with Image.open(base_image_path).convert("RGBA") as base:
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        layout_width, layout_height = layout["image_size"]
        scale_x = base.width / layout_width
        scale_y = base.height / layout_height
        for annotation in plan["annotations"]:
            slot_box = layout["slots"][annotation["slot"]]
            scaled_box = _scale_box(slot_box, scale_x, scale_y)
            resolved_box = _resolve_box_for_mark(base, layout, annotation["slot"], scaled_box, annotation["type"])
            _apply_mark(overlay, resolved_box, annotation["type"])
        Image.alpha_composite(base, overlay).save(output_path)
    print(f"{matchup_name}: {output_path}")
    return output_path


def _collect_plans(config: dict, config_path: Path) -> dict[str, dict]:
    collections: list[dict[str, dict]] = []
    if isinstance(config.get("plans"), dict):
        collections.append(config["plans"])
    if isinstance(config.get("slides"), dict):
        collections.append(config["slides"])
    if not collections:
        legacy_name = config.get("plan_name", config_path.stem)
        return {legacy_name: {"type": "sideboard", "output_image": config["output_image"], "annotations": config["annotations"]}}

    merged: dict[str, dict] = {}
    for collection in collections:
        for plan_name, plan in collection.items():
            if plan_name in merged:
                raise ValueError(f"Duplicate plan name '{plan_name}' found across plans/slides collections.")
            merged[plan_name] = plan
    return merged


def _resolve_plan_selection(config: dict, config_path: Path, requested_matchup: str | None) -> list[tuple[str, dict]]:
    plans = _collect_plans(config, config_path)
    if requested_matchup is None:
        return list(plans.items())
    requested_slug = _slug(requested_matchup)
    for matchup_name, plan in plans.items():
        if matchup_name == requested_matchup or _slug(matchup_name) == requested_slug:
            return [(matchup_name, plan)]
    raise ValueError(f"Unknown plan '{requested_matchup}'. Available plans: {', '.join(plans.keys())}")


def _filter_plan_selection(plans: list[tuple[str, dict]], allowed_types: set[str] | None) -> list[tuple[str, dict]]:
    if allowed_types is None:
        return plans

    filtered = [(plan_name, plan) for plan_name, plan in plans if plan.get("type", "sideboard") in allowed_types]
    if filtered:
        return filtered

    supported = ", ".join(sorted(allowed_types))
    available = ", ".join(f"{plan_name} ({plan.get('type', 'sideboard')})" for plan_name, plan in plans) or "none"
    raise ValueError(f"No plans of type {supported} were found. Available plans: {available}")


def _render_plan(
    deck_dir: Path,
    config: dict,
    layout: dict | None,
    base_image_path: Path | None,
    matchup_name: str,
    plan: dict,
    resolver: CardAssetResolver,
) -> Path:
    plan_type = plan.get("type", "sideboard")
    if plan_type == "sideboard":
        if layout is None or base_image_path is None:
            raise ValueError("Sideboard plans require both layout and base_image.")
        return _render_sideboard_plan(deck_dir, config, layout, base_image_path, matchup_name, plan)
    if plan_type == "decklist":
        return _draw_decklist_plan(deck_dir, config, _resolve_output_path(deck_dir, config, plan), matchup_name, plan, resolver)
    if plan_type == "informative":
        return _draw_informative_slide(deck_dir, config, _resolve_output_path(deck_dir, config, plan), matchup_name, plan, resolver)
    if plan_type == "follow_up":
        return _draw_follow_up_slide(deck_dir, config, _resolve_output_path(deck_dir, config, plan), matchup_name, plan, resolver)
    if plan_type == "feature":
        return _draw_feature_slide(deck_dir, config, _resolve_output_path(deck_dir, config, plan), matchup_name, plan, resolver)
    raise ValueError(f"Unsupported plan type: {plan_type}")


def render_from_config_path(config_path: Path, requested_matchup: str | None = None, *, allowed_types: set[str] | None = None) -> list[Path]:
    config_path = config_path.resolve()
    deck_dir = config_path.parent
    config = _load_json(config_path)
    _ensure_imports(deck_dir, config)

    layout = _load_json(deck_dir / config["layout"]) if config.get("layout") else None
    base_image_path = deck_dir / config["base_image"] if config.get("base_image") else None
    resolver = CardAssetResolver(deck_dir, config)

    rendered_paths = []
    selected_plans = _filter_plan_selection(_resolve_plan_selection(config, config_path, requested_matchup), allowed_types)
    for matchup_name, plan in selected_plans:
        rendered_paths.append(_render_plan(deck_dir, config, layout, base_image_path, matchup_name, plan, resolver))
    return rendered_paths


def main(*, script_name: str = "generate_sideboard_guide.py", allowed_types: set[str] | None = None) -> int:
    if len(sys.argv) not in (2, 3):
        return _usage(script_name)

    config_path = Path(sys.argv[1])
    requested_matchup = sys.argv[2] if len(sys.argv) == 3 else None
    render_from_config_path(config_path, requested_matchup, allowed_types=allowed_types)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
