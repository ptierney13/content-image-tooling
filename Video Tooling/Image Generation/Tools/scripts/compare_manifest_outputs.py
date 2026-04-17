import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat


IMAGE_GENERATION_DIR = Path(__file__).resolve().parents[2]
VERIFICATION_DIR = IMAGE_GENERATION_DIR / "output" / "_verification"
COMPARISON_DIR = VERIFICATION_DIR / "comparisons"


def _resolve(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else IMAGE_GENERATION_DIR / path


def _slug(text: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "comparison"


def _fit_for_preview(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    preview = image.convert("RGBA")
    preview.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return preview


def _draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    font = ImageFont.load_default()
    x, y = xy
    draw.rectangle((x - 8, y - 6, x + 8 + len(text) * 7, y + 18), fill=(0, 0, 0, 210))
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)


def _write_side_by_side(name: str, reference: Image.Image, generated: Image.Image, difference: Image.Image | None) -> Path:
    COMPARISON_DIR.mkdir(parents=True, exist_ok=True)
    max_width = 760
    max_height = 520
    ref_preview = _fit_for_preview(reference, max_width, max_height)
    gen_preview = _fit_for_preview(generated, max_width, max_height)

    panels = [("reference", ref_preview), ("new", gen_preview)]
    if difference is not None:
        diff_preview = _fit_for_preview(difference, max_width, max_height)
        panels.append(("difference", diff_preview))

    gutter = 24
    label_height = 34
    width = sum(panel.width for _, panel in panels) + gutter * (len(panels) + 1)
    height = max(panel.height for _, panel in panels) + gutter * 2 + label_height
    canvas = Image.new("RGBA", (width, height), (22, 24, 30, 255))
    draw = ImageDraw.Draw(canvas)

    x = gutter
    for label, panel in panels:
        _draw_label(draw, (x, gutter), label)
        canvas.alpha_composite(panel, (x, gutter + label_height))
        x += panel.width + gutter

    output_path = COMPARISON_DIR / f"{_slug(name)}.png"
    canvas.convert("RGB").save(output_path)
    return output_path


def _compare_images(item: dict, *, write_all: bool) -> dict:
    reference_path = _resolve(item["reference"])
    generated_path = _resolve(item["new_output"])
    result = {
        "name": item["name"],
        "reference": str(reference_path),
        "new_output": str(generated_path),
        "match": False,
        "details": "",
        "comparison": None,
    }

    if not reference_path.exists():
        result["details"] = "Reference image is missing."
        return result
    if not generated_path.exists():
        result["details"] = "Generated image is missing."
        return result

    with Image.open(reference_path).convert("RGBA") as reference, Image.open(generated_path).convert("RGBA") as generated:
        if reference.size != generated.size:
            result["details"] = f"Size mismatch: reference {reference.size[0]}x{reference.size[1]}, new {generated.size[0]}x{generated.size[1]}."
            comparison = _write_side_by_side(item["name"], reference, generated, None)
            result["comparison"] = str(comparison)
            return result

        diff = ImageChops.difference(reference, generated)
        bbox = diff.getbbox()
        if bbox is None:
            result["match"] = True
            result["details"] = "Exact pixel match."
            if write_all:
                result["comparison"] = str(_write_side_by_side(item["name"], reference, generated, None))
            return result

        stat = ImageStat.Stat(diff)
        rms = math.sqrt(sum(value * value for value in stat.rms[:3]) / 3)
        result["details"] = f"Pixel mismatch: bbox={bbox}, rms={rms:.4f}."
        boosted_diff = diff.point(lambda value: min(255, value * 8))
        result["comparison"] = str(_write_side_by_side(item["name"], reference, generated, boosted_diff))
        return result


def _write_reports(results: list[dict]) -> None:
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    mismatches = [result for result in results if not result["match"]]
    payload = {
        "total": len(results),
        "matches": len(results) - len(mismatches),
        "mismatches": mismatches,
        "results": results,
    }
    (VERIFICATION_DIR / "comparison-report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    lines = [
        "# Image Comparison Report",
        "",
        f"- Total: {payload['total']}",
        f"- Matches: {payload['matches']}",
        f"- Mismatches: {len(mismatches)}",
        "",
    ]
    for result in results:
        status = "match" if result["match"] else "mismatch"
        lines.append(f"## {result['name']}")
        lines.append(f"- Status: {status}")
        lines.append(f"- Details: {result['details']}")
        if result["comparison"]:
            comparison = Path(result["comparison"]).resolve()
            lines.append(f"![{result['name']}]({comparison})")
        lines.append("")

    (VERIFICATION_DIR / "comparison-report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare manifest outputs against preserved reference images.")
    parser.add_argument("manifest", help="Path to Data/render-manifest.json, relative to Image Generation or absolute.")
    parser.add_argument("--all", action="store_true", help="Write side-by-side comparisons for matching images too.")
    args = parser.parse_args()

    manifest = json.loads(_resolve(args.manifest).read_text(encoding="utf-8-sig"))
    results = [_compare_images(item, write_all=args.all) for item in manifest.get("items", [])]
    _write_reports(results)

    mismatches = [result for result in results if not result["match"]]
    print(f"Compared {len(results)} image(s): {len(results) - len(mismatches)} match, {len(mismatches)} mismatch.")
    for result in mismatches:
        print(f"mismatch: {result['name']} - {result['details']}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
