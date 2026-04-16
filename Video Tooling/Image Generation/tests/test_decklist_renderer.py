import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SHARED_DIR = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import render_image_plans as rip


def _write_test_image(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path)


class DecklistRendererTests(unittest.TestCase):
    def test_parse_decklist_text_groups_entries_by_section(self) -> None:
        raw_text = """
Legend:
1 Ezreal, Prodigal Explorer

Champion:
1 Ezreal, Prodigy

MainDeck:
3 Stupefy
2 Gust

Battlefields:
1 Fortified Position

Runes:
7 Chaos Rune
5 Mind Rune

Sideboard:
2 Retreat
""".strip()

        parsed = rip._parse_decklist_text(raw_text)

        self.assertEqual([section["key"] for section in parsed["sections"]], ["legend", "champion", "maindeck", "battlefields", "runes", "sideboard"])
        self.assertEqual(parsed["by_key"]["legend"]["entries"][0]["card_name"], "Ezreal, Prodigal Explorer")
        self.assertEqual(parsed["by_key"]["maindeck"]["entries"][1]["count"], 2)
        self.assertEqual(parsed["by_key"]["runes"]["entries"][0]["count"], 7)

    def test_rune_entries_are_ordered_by_legend_slot_color(self) -> None:
        entries = [
            {"count": 7, "card_name": "Chaos Rune"},
            {"count": 5, "card_name": "Mind Rune"},
        ]
        slot_symbols = [
            Image.new("RGBA", (94, 94), (22, 81, 126, 255)),
            Image.new("RGBA", (94, 94), (74, 55, 125, 255)),
        ]

        ordered_entries, ordered_slots = rip._order_rune_entries_for_legend_slots(entries, slot_symbols)

        self.assertEqual([entry["card_name"] for entry in ordered_entries], ["Mind Rune", "Chaos Rune"])
        self.assertEqual([entry["count"] for entry in ordered_entries], [5, 7])
        self.assertEqual(ordered_slots, [0, 1])

    def test_decklist_title_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "deck_name/title"):
            rip._resolve_decklist_title({}, {"type": "decklist"})

    def test_battlefield_labels_are_required(self) -> None:
        entries = [{"count": 1, "card_name": "Fortified Position"}]

        with self.assertRaisesRegex(ValueError, "battlefield labels are required"):
            rip._ensure_battlefield_labels(entries)

    def test_strict_official_assets_reject_generic_image_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = rip.CardAssetResolver(Path(temp_dir), {"card_assets": {"require_official_assets": True}})

            with self.assertRaisesRegex(ValueError, "official source"):
                resolver.resolve_card_path({"card_name": "Test Card", "image_url": "https://example.com/card.png"})

    def test_catalog_local_path_is_preferred_over_redownload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_dir = Path(temp_dir)
            local_image = deck_dir / "official" / "test-card.png"
            _write_test_image(local_image, (300, 420), (100, 140, 220, 255))

            resolver = rip.CardAssetResolver(
                deck_dir,
                {
                    "card_assets": {
                        "require_official_assets": True,
                        "catalogs": [
                            {
                                "cards": [
                                    {
                                        "name": "Test Card",
                                        "official_image_url": "https://example.com/test-card.png",
                                        "local_path": str(local_image.relative_to(deck_dir)),
                                    }
                                ]
                            }
                        ],
                    }
                },
            )

            resolved = resolver.resolve_card_path({"card_name": "Test Card"})

            self.assertEqual(resolved, local_image)

    def test_alias_names_are_registered_for_catalog_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_dir = Path(temp_dir)
            local_image = deck_dir / "official" / "legend.png"
            _write_test_image(local_image, (300, 420), (180, 120, 60, 255))

            resolver = rip.CardAssetResolver(
                deck_dir,
                {
                    "card_assets": {
                        "require_official_assets": True,
                        "catalogs": [
                            {
                                "cards": [
                                    {
                                        "name": "Prodigal Explorer",
                                        "aliases": ["Ezreal, Prodigal Explorer"],
                                        "local_path": str(local_image.relative_to(deck_dir)),
                                    }
                                ]
                            }
                        ],
                    }
                },
            )

            resolved = resolver.resolve_card_path({"card_name": "Ezreal, Prodigal Explorer"})

            self.assertEqual(resolved, local_image)

    def test_decklist_plan_renders_from_plaintext_and_local_official_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_dir = Path(temp_dir)
            official_dir = deck_dir / "official"

            assets = {
                "Ezreal, Prodigal Explorer": ("legend.png", (720, 1020), (180, 120, 60, 255)),
                "Ezreal, Prodigy": ("champion.png", (720, 1020), (90, 110, 210, 255)),
                "Stupefy": ("stupefy.png", (720, 1020), (120, 90, 190, 255)),
                "Gust": ("gust.png", (720, 1020), (80, 160, 220, 255)),
                "Sneaky Deckhand": ("deckhand.png", (720, 1020), (130, 90, 60, 255)),
                "Fizz, Trickster": ("fizz.png", (720, 1020), (60, 150, 170, 255)),
                "Fortified Position": ("fortified-position.png", (1200, 720), (140, 90, 90, 255)),
                "The Arena's Greatest": ("arena.png", (1200, 720), (180, 120, 90, 255)),
                "Retreat": ("retreat.png", (720, 1020), (120, 150, 90, 255)),
                "Factory Recall": ("factory-recall.png", (720, 1020), (90, 170, 150, 255)),
                "Rebuke": ("rebuke.png", (720, 1020), (150, 90, 160, 255)),
            }

            catalog_records = []
            for card_name, (filename, size, color) in assets.items():
                image_path = official_dir / filename
                _write_test_image(image_path, size, color)
                catalog_records.append({"name": card_name, "local_path": str(image_path.relative_to(deck_dir))})

            decklist_path = deck_dir / "decklist.txt"
            decklist_path.write_text(
                """
Legend:
1 Ezreal, Prodigal Explorer

Champion:
1 Ezreal, Prodigy

MainDeck:
3 Stupefy
3 Gust
2 Sneaky Deckhand
1 Fizz, Trickster

Battlefields:
1 Fortified Position | Play
1 The Arena's Greatest | Draw

Runes:
7 Chaos Rune
5 Mind Rune

Sideboard:
2 Retreat
2 Factory Recall
1 Rebuke
""".strip(),
                encoding="utf-8",
            )

            catalog_path = deck_dir / "official-catalog.json"
            catalog_path.write_text(json.dumps(catalog_records, indent=2), encoding="utf-8")

            config_path = deck_dir / "decklist-render.json"
            config_path.write_text(
                json.dumps(
                    {
                        "decklist_path": "decklist.txt",
                        "card_assets": {
                            "require_official_assets": True,
                            "catalogs": ["official-catalog.json"],
                        },
                        "plans": {
                            "Ezreal Tempo": {
                                "type": "decklist",
                                "deck_name": "Ezreal Tempo",
                                "subtitle": "Set 2",
                                "canvas_size": [1600, 900],
                                "output_dir": "Deck Images",
                                "output_image": "ezreal-tempo.png",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            rendered_paths = rip.render_from_config_path(config_path)

            self.assertEqual(len(rendered_paths), 1)
            self.assertTrue(rendered_paths[0].exists())
            with Image.open(rendered_paths[0]) as rendered:
                self.assertEqual(rendered.size, (1600, 900))


if __name__ == "__main__":
    unittest.main()
