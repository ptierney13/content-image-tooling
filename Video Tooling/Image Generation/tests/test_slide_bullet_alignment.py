import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw


SHARED_DIR = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import render_image_plans as rip


class BulletAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = Image.new("RGBA", (900, 700), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.font = rip._load_font(42)

    def test_bullet_anchor_center_matches_first_letter_center(self) -> None:
        line_y = 200
        samples = [
            "Be aggressive, every point matters",
            "Defend battlefields when possible",
            "Strand their Ruin Runners",
            "Dig for Thousand-Tailed Watcher",
            "Don't play scared, make them have it",
        ]

        for text in samples:
            with self.subTest(text=text):
                first_letter = next(character for character in text if character.isalpha())
                _, top, _, bottom = self.draw.textbbox((0, 0), first_letter, font=self.font)
                expected_center = line_y + round((top + bottom) / 2)
                self.assertEqual(rip._bullet_anchor_center_y(self.draw, text, self.font, line_y), expected_center)

    def test_bullet_anchor_center_ignores_leading_punctuation(self) -> None:
        line_y = 200
        text = "\"Be aggressive, every point matters\""
        _, top, _, bottom = self.draw.textbbox((0, 0), "B", font=self.font)
        expected_center = line_y + round((top + bottom) / 2)

        self.assertEqual(rip._bullet_anchor_center_y(self.draw, text, self.font, line_y), expected_center)

    def test_informative_slide_uses_anchor_center_for_each_bullet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_dir = Path(temp_dir)
            output_path = deck_dir / "verify.png"
            plan = {
                "type": "informative",
                "title": "Verify Matchup Summary",
                "output_path": str(output_path),
                "background": {"kind": "pattern"},
                "body_font_size": 42,
                "text_top": 226,
                "text_bottom": 820,
                "line_spacing": 10,
                "bullet_spacing": 34,
                "bullets": [
                    "Be aggressive, every point matters",
                    "Defend battlefields when possible",
                    "Strand their Ruin Runners",
                    "Dig for Thousand-Tailed Watcher",
                    "Don't play scared, make them have it",
                ],
            }
            resolver = rip.CardAssetResolver(deck_dir, {})

            recorded_centers: list[int] = []

            original_draw_bullet_icon = rip._draw_bullet_icon

            def capture_bullet_icon(draw: ImageDraw.ImageDraw, center: tuple[int, int], style: str) -> None:
                recorded_centers.append(center[1])
                original_draw_bullet_icon(draw, center, style)

            with patch.object(rip, "_draw_bullet_icon", side_effect=capture_bullet_icon):
                rip._draw_informative_slide(deck_dir, {}, output_path, "Verify Matchup Summary", plan, resolver)

            verification_canvas = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
            verification_draw = ImageDraw.Draw(verification_canvas)
            body_font = rip._load_font(plan["body_font_size"])
            text_left = 100
            text_width = 1536 - text_left - 86
            bullet_indent = 46
            line_spacing = plan["line_spacing"]
            current_y = plan["text_top"]
            wrapped_layouts = []

            for bullet in plan["bullets"]:
                lines = rip._wrap_text(verification_draw, bullet, body_font, text_width - bullet_indent)
                line_heights = [rip._text_size(verification_draw, line, body_font)[1] for line in lines]
                total_height = sum(line_heights) + (line_spacing * max(0, len(lines) - 1))
                wrapped_layouts.append({"lines": lines, "total_height": total_height, "line_heights": line_heights})

            total_bullet_height = sum(layout["total_height"] for layout in wrapped_layouts)
            bullet_spacing = (plan["text_bottom"] - current_y - total_bullet_height) // (len(wrapped_layouts) - 1)

            expected_centers = []
            for layout in wrapped_layouts:
                expected_centers.append(rip._bullet_anchor_center_y(verification_draw, layout["lines"][0], body_font, current_y))
                line_y = current_y
                for line_height in layout["line_heights"]:
                    line_y += line_height + line_spacing
                current_y = line_y + bullet_spacing

            self.assertEqual(recorded_centers, expected_centers)


if __name__ == "__main__":
    unittest.main()
