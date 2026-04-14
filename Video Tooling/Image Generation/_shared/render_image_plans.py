import hashlib
import json
import math
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
SIDEBOARD_PLAN_TYPES = {"sideboard"}
SLIDE_PLAN_TYPES = {"informative", "follow_up"}


def _usage(script_name: str) -> int:
    print(f"Usage: python {script_name} <plans.json> [plan]")
    print("Plan types: sideboard (default), informative, follow_up")
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
    for folder_name in ("Maindeck", "References"):
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

    def resolve_card_path(self, card: dict) -> Path:
        explicit_url = _first_value(card.get("riot_image_url"), card.get("image_url"), card.get("render_url"))
        if explicit_url:
            return self._download_to_cache(explicit_url, hint=_first_value(card.get("card_name"), card.get("name"), card.get("card_code")))

        local_path = _first_value(card.get("local_path"), card.get("path"))
        if local_path:
            return _resolve_deck_path(self.deck_dir, local_path)

        record = self._resolve_card_record(card)
        resolved_url = self._record_image_url(record)
        if resolved_url:
            return self._download_to_cache(resolved_url, hint=_first_value(record.get("name"), record.get("cardCode")))

        resolved_path = _first_value(record.get("local_path"), record.get("path"))
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

    def _record_image_url(self, record: dict) -> str | None:
        assets = record.get("assets")
        if isinstance(assets, list) and assets:
            primary_asset = assets[0]
            if isinstance(primary_asset, dict):
                return _first_value(primary_asset.get("gameAbsolutePath"), primary_asset.get("render_url"), primary_asset.get("image_url"))
        return _first_value(record.get("riot_image_url"), record.get("image_url"), record.get("render_url"), record.get("gameAbsolutePath"))

    def _download_to_cache(self, url: str, *, hint: str | None) -> Path:
        suffix = Path(urlparse(url).path).suffix or ".png"
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        destination = self.cache_dir / f"{_filename_slug(hint or 'card')}-{digest}{suffix}"
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


def _resolve_output_path(deck_dir: Path, config: dict, plan: dict) -> Path:
    output_path = plan.get("output_path")
    if output_path:
        resolved = _resolve_deck_path(deck_dir, output_path)
    else:
        output_dir = _resolve_deck_path(deck_dir, plan.get("output_dir") or config.get("output_dir", "Sideboard Guides"))
        output_name = plan.get("output_image")
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
    if not bullets:
        raise ValueError("Informative slides require a non-empty bullets list.")

    body_font = _load_font(plan.get("body_font_size", 46), bold=False)
    text_left = 100 if not cards else 635
    text_width = size[0] - text_left - 86
    current_y = plan.get("text_top", 312 if cards else 238)
    line_spacing = plan.get("line_spacing", 14)
    bullet_spacing = plan.get("bullet_spacing", 34)
    bullet_indent = plan.get("bullet_indent", 46)
    bullet_style = plan.get("bullet_style", "dot")
    text_bottom = plan.get("text_bottom")
    _, reference_height = _text_size(draw, "Ag", body_font)

    bullet_layouts = []
    for bullet in bullets:
        text = bullet["text"] if isinstance(bullet, dict) else str(bullet)
        style = bullet.get("style", bullet_style) if isinstance(bullet, dict) else bullet_style
        lines = _wrap_text(draw, text, body_font, text_width - bullet_indent)
        line_heights = [_text_size(draw, line, body_font)[1] for line in lines]
        total_height = sum(line_heights) + (line_spacing * max(0, len(lines) - 1))
        bullet_layouts.append(
            {
                "style": style,
                "lines": lines,
                "line_heights": line_heights,
                "total_height": total_height,
            }
        )

    if text_bottom is not None and len(bullet_layouts) > 1:
        total_bullet_height = sum(layout["total_height"] for layout in bullet_layouts)
        available_gap = int(text_bottom) - int(current_y) - total_bullet_height
        bullet_spacing = max(0, math.floor(available_gap / (len(bullet_layouts) - 1)))

    for bullet_layout in bullet_layouts:
        bullet_center_y = current_y + math.floor(bullet_layout["line_heights"][0] / 2)
        _draw_bullet_icon(draw, (text_left, bullet_center_y), bullet_layout["style"])
        line_y = current_y
        for line, line_height in zip(bullet_layout["lines"], bullet_layout["line_heights"]):
            _draw_text_with_shadow(draw, (text_left + bullet_indent, line_y), line, body_font, SLIDE_TEXT, shadow_offset=(2, 2))
            line_y += line_height + line_spacing
        current_y = line_y + bullet_spacing

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
    if plan_type == "informative":
        return _draw_informative_slide(deck_dir, config, _resolve_output_path(deck_dir, config, plan), matchup_name, plan, resolver)
    if plan_type == "follow_up":
        return _draw_follow_up_slide(deck_dir, config, _resolve_output_path(deck_dir, config, plan), matchup_name, plan, resolver)
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
