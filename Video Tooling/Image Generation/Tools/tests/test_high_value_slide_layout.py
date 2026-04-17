import sys
import unittest
from pathlib import Path

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_image_plans as rip


IMAGE_GENERATION_DIR = Path(__file__).resolve().parents[2]
PLAN_PATH = IMAGE_GENERATION_DIR / "output" / "Ezreal Tempo" / "Data" / "slide-plans.json"
PLAN_NAME = "High Value Card Options"


class HighValueSlideLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = rip._load_json(PLAN_PATH)
        self.deck_dir = PLAN_PATH.parent
        self.plan = self.config["plans"][PLAN_NAME]
        base_slide = rip._resolve_deck_path(self.deck_dir, self.plan["base_slide"])
        with Image.open(base_slide) as source:
            default_size = source.size
        self.size = rip._resolve_size(rip._first_value(self.plan.get("canvas_size"), default_size, self.config.get("canvas_size")))
        self.midline_y = int(self.plan["layout_notes"]["aligned_card_midline_y"])

    def test_high_value_slide_locks_one_battlefield_two_card_layout(self) -> None:
        self.assertEqual([card["card_name"] for card in self.plan["cards"]], ["Void Gate", "Unchecked Power", "Downwell"])

        void_gate = self.plan["cards"][0]
        unchecked_power = self.plan["cards"][1]
        self.assertEqual(void_gate["layout_role"], "battlefield")
        self.assertNotIn("layout_role", unchecked_power)
        self.assertNotIn("layout_role", self.plan["cards"][2])

        gap_midpoint = (int(void_gate["box"][2]) + int(unchecked_power["box"][0])) / 2

        self.assertEqual(gap_midpoint, self.plan["layout_notes"]["battlefield_to_first_portrait_gap_midpoint_x"])

    def test_high_value_cards_share_the_same_horizontal_midline(self) -> None:
        expected_midline = self.plan["layout_notes"]["aligned_card_midline_y"]

        for card in self.plan["cards"]:
            with self.subTest(card=card["card_name"]):
                top = int(card["box"][1])
                bottom = int(card["box"][3])
                self.assertEqual((top + bottom) / 2, expected_midline)

        self.assertEqual(self.plan["layout_notes"]["battlefield_box"], self.plan["cards"][0]["box"])

    def test_high_value_cards_use_locked_final_offset_from_baseline(self) -> None:
        shift_px = self.plan["layout_notes"]["card_shift_px"]
        shift_fraction = self.plan["layout_notes"]["card_shift_fraction_of_image_width"]
        self.assertEqual(shift_px, round(self.size[0] * shift_fraction))

        self.assertEqual(self.plan["cards"][0]["box"], [128 + shift_px, 392, 728 + shift_px, 818])
        self.assertEqual(self.plan["cards"][1]["box"], [808 + shift_px, 370, 1148 + shift_px, 840])
        self.assertEqual(self.plan["cards"][2]["box"], [1184 + shift_px, 370, 1524 + shift_px, 840])


if __name__ == "__main__":
    unittest.main()
