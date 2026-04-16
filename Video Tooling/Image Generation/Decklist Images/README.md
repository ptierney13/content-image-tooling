# Decklist Images

This workflow now supports two deck-focused image types:

- annotated deck exports for sideboarding guides
- original decklist posters rendered from plaintext decklists plus official Riftbound card assets

Use it to render matchup-specific sideboard guides with `X`, `-1`, and check marks over a canonical maindeck screenshot.
It can also render a full decklist image from a decklist text file without relying on a third-party generated screenshot.

## Primary Command

Run these commands from `Video Tooling\Image Generation` so the shared cache and deck-local render scripts resolve consistently:

```powershell
python scripts/sync_official_riftbound_assets.py --decklist-file "Decklist Images\Set 2\Ezreal Tempo\decklist.txt"
python "Decklist Images\scripts\generate_decklist_image.py" "Decklist Images\Set 2\Ezreal Tempo\sideboard-plans.json"
python "Decklist Images\scripts\generate_decklist_image.py" "Decklist Images\Set 2\Ezreal Tempo\sideboard-plans.json" "Irelia"
python "Decklist Images\scripts\generate_decklist_image.py" "Decklist Images\Set 2\Ezreal Tempo\decklist-render.json"
```

## Compatibility Command

Older commands still work:

```powershell
python scripts/generate_sideboard_guide.py "Set 2\Ezreal Tempo\sideboard-plans.json"
```

## Plan File Shape

```json
{
  "layout": "layout.json",
  "base_image": "Maindeck/ezreal-tempo-maindeck.png",
  "output_dir": "Sideboard Guides",
  "plans": {
    "Irelia": {
      "type": "sideboard",
      "output_image": "irelia-matchup-sb-guide.png",
      "annotations": [
        { "slot": "maindeck.bellows_breath", "type": "x" },
        { "slot": "sideboard.hard_bargain", "type": "check" }
      ]
    }
  }
}
```

For original decklist posters, use a dedicated config file that points at a plaintext decklist and an official asset catalog or local official exports:

```json
{
  "decklist_path": "decklist.txt",
  "card_assets": {
    "require_official_assets": true,
    "catalogs": [
      "References/riftbound-card-catalog.json"
    ]
  },
  "plans": {
    "Ezreal Tempo": {
      "type": "decklist",
      "deck_name": "Ezreal Tempo",
      "subtitle": "Set 2",
      "output_dir": "Deck Images",
      "output_image": "ezreal-tempo.png",
      "background": {
        "accent_color": [214, 178, 102, 255]
      }
    }
  }
}
```

The shared official cache created by `scripts/sync_official_riftbound_assets.py` lives at:

- `Image Generation/_card_cache/riftbound-official/catalog-en-us.json`
- `Image Generation/_card_cache/riftbound-official/images/`

The sync script pulls the official card gallery feed from `riftbound.leagueoflegends.com`, normalizes it into a reusable catalog, and can prefetch every card named in a plaintext decklist into that shared cache.

## Future Decklist Setup

Before creating or rendering a new decklist poster, stop and confirm these two user-provided details:

- Deck title: do not infer it from the Legend, file name, folder name, or plan key.
- Battlefield roles: if any `Battlefields:` line does not include a `| Play`, `| Draw`, or `| Game 1` label, ask which battlefield is which before rendering.

For a new deck, create a deck folder such as `Decklist Images\Set <N>\<Deck Name>\` and add:

- `decklist.txt`
- `decklist-render.json`
- `Deck Images\` for rendered poster outputs

Start from `decklist-render.template.json` when creating the deck-local `decklist-render.json`.

Use this cache-backed asset block in `decklist-render.json` so every deck shares the same official downloads:

```json
{
  "card_assets": {
    "require_official_assets": true,
    "cache_dir": "../../../_card_cache/riftbound-official/images",
    "catalogs": [
      "../../../_card_cache/riftbound-official/catalog-en-us.json"
    ]
  }
}
```

Before rendering, sync any missing official cards from the plaintext decklist:

```powershell
python scripts/sync_official_riftbound_assets.py --decklist-file "Decklist Images\Set <N>\<Deck Name>\decklist.txt"
```

Then render the poster:

```powershell
python "Decklist Images\scripts\generate_decklist_image.py" "Decklist Images\Set <N>\<Deck Name>\decklist-render.json"
```

Rune symbols are cropped from the official Legend card image, not generated separately. The renderer uses normalized crop boxes for the two rune slots in the top-left Legend-card frame, so future Legend cards should reuse the same symbol positions as long as Riot's official Legend frame remains consistent. The order in the `Runes:` section does not matter; the poster displays runes in Legend-card order and pairs counts to the matching rune names.

Decklist poster plans accept either:

- `decklist_path` / `decklist_file`
- `decklist_text` / `decklist`

The expected plaintext format is:

```text
Legend:
1 Ezreal, Prodigal Explorer

Champion:
1 Ezreal, Prodigy

MainDeck:
3 Stupefy
...

Battlefields:
1 Fortified Position | Play
1 The Arena's Greatest | Draw
1 Marai Spire | Game 1
```

## Notes

- `layout.json` remains the source of truth for slot geometry.
- `sideboard-plans.json` remains the source of truth for matchup annotations.
- Decklist poster plans should live in their own config file such as `decklist-render.json`.
- Decklist poster renders default to `Deck Images/` unless `output_dir` is overridden.
- Decklist poster renders must use official Riftbound assets only: `official_image_url` / `riot_image_url`, `assets[].gameAbsolutePath` from an official catalog, or `local_path` to a locally cached official export.
- Prefer `scripts/sync_official_riftbound_assets.py` plus the shared `_card_cache/riftbound-official/` directory for reusable official catalogs and local image caching across decks.
- Avoid third-party-hosted card art for decklist poster renders.
- Slide rendering has moved to [Slides/README.md](../Slides/README.md).
