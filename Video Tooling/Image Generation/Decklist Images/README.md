# Decklist Images

This workflow is for annotated deck exports only.

Use it to render matchup-specific sideboard guides with `X`, `-1`, and check marks over a canonical maindeck screenshot.

## Primary Command

```powershell
python scripts/generate_decklist_image.py "Set 2\Ezreal Tempo\sideboard-plans.json"
python scripts/generate_decklist_image.py "Set 2\Ezreal Tempo\sideboard-plans.json" "Irelia"
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

## Notes

- `layout.json` remains the source of truth for slot geometry.
- `sideboard-plans.json` remains the source of truth for matchup annotations.
- Slide rendering has moved to [Slides/README.md](../Slides/README.md).
