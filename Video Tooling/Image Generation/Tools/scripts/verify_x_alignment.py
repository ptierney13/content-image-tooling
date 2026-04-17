import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import render_image_plans as guide


DEFAULT_SLOTS = [
    "maindeck.bellows_breath",
    "maindeck.plundering_poro",
    "maindeck.ravenbloom_student",
    "maindeck.rebuke",
    "maindeck.singularity",
    "maindeck.thousand_tailed_watcher",
]


def _usage() -> int:
    print("Usage: python verify_x_alignment.py <deck-dir> [slot ...]")
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        return _usage()

    deck_dir = Path(sys.argv[1]).resolve()
    slots = sys.argv[2:] or DEFAULT_SLOTS

    layout_path = deck_dir / "layout.json"
    plans_path = deck_dir / "sideboard-plans.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    plans = json.loads(plans_path.read_text(encoding="utf-8"))
    base_image_path = deck_dir / plans["base_image"]
    output_path = deck_dir / ".." / "_verification" / "x-alignment-sheet.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(base_image_path).convert("RGBA") as base:
        crops = []
        for slot in slots:
            slot_box = tuple(layout["slots"][slot])
            resolved_box = guide._resolve_box_for_mark(base, layout, slot, slot_box, "x")
            marker_center_x = (resolved_box[0] + resolved_box[2]) / 2

            canvas = base.copy()
            overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            guide._apply_mark(overlay, resolved_box, "x")
            canvas = Image.alpha_composite(canvas, overlay)

            draw = ImageDraw.Draw(canvas)
            draw.line((marker_center_x, resolved_box[1], marker_center_x, resolved_box[3]), fill=(0, 255, 255, 255), width=3)

            crop_left = max(0, int(slot_box[0] - 18))
            crop_top = max(0, int(slot_box[1] - 18))
            crop_right = min(canvas.width, int(slot_box[2] + 18))
            crop_bottom = min(canvas.height, int(slot_box[3] + 18))
            crop = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))
            crops.append(crop)

        columns = 3
        rows = (len(crops) + columns - 1) // columns
        cell_width = max(crop.width for crop in crops)
        cell_height = max(crop.height for crop in crops)
        sheet = Image.new("RGBA", (cell_width * columns, cell_height * rows), (22, 22, 22, 255))

        for index, crop in enumerate(crops):
            x = (index % columns) * cell_width
            y = (index // columns) * cell_height
            sheet.alpha_composite(crop, (x, y))

        sheet.save(output_path)

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
