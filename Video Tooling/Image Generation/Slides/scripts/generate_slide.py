import sys
from pathlib import Path


SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from render_image_plans import SLIDE_PLAN_TYPES, main


if __name__ == "__main__":
    raise SystemExit(main(script_name=Path(__file__).name, allowed_types=SLIDE_PLAN_TYPES))
