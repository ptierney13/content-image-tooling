# Image Generation

This folder is organized around repeatable generation instead of workflow silos.

- `Data/` stores shared card caches, templates, and the render manifest.
- `Tools/` stores scripts, tests, and agent execution notes.
- `output/` stores the current deck outputs and the deck-specific data that produces them.

Run commands from `Video Tooling/Image Generation` unless a script says otherwise.

```powershell
python Tools\scripts\sync_official_riftbound_assets.py --decklist-file "output\Ezreal Tempo\Data\decklist.txt" --decklist-file "output\Lee Sin Centered\Data\decklist.txt" --card "Void Gate" --card "Unchecked Power" --card "Downwell"
python Tools\scripts\regenerate_manifest.py Data\render-manifest.json
python -m unittest discover Tools\tests
```

`Data/card-cache/` is intentionally ignored by git. Each clone should sync the official cache locally before regenerating outputs.
