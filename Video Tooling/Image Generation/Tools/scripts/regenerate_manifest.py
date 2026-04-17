import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_image_plans as rip


IMAGE_GENERATION_DIR = Path(__file__).resolve().parents[2]


def _resolve(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else IMAGE_GENERATION_DIR / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate every finalized image listed in a render manifest.")
    parser.add_argument("manifest", help="Path to Data/render-manifest.json, relative to Image Generation or absolute.")
    args = parser.parse_args()

    manifest_path = _resolve(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    rendered = []

    for item in manifest.get("items", []):
        config_path = _resolve(item["config"])
        plan_name = item["plan"]
        outputs = rip.render_from_config_path(config_path, plan_name)
        expected_output = _resolve(item["new_output"])
        if expected_output not in outputs and not expected_output.exists():
            raise RuntimeError(f"{item['name']} did not produce expected output: {expected_output}")
        rendered.append(str(expected_output))
        print(f"rendered: {item['name']} -> {expected_output}")

    print(f"Regenerated {len(rendered)} image(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
