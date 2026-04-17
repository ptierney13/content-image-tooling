# Image Generation

## Layout
- `Data/`: shared card cache, templates, and reusable reference data for image generation.
- `Tools/`: scripts, tests, and agent execution docs.
- `output/`: finalized deck images and deck-specific source data.

## Output Contract
Each deck folder under `output/` should use this shape:

```text
output/
  <Deck Name>/
    maindeck.png
    Data/
      decklist.txt
      decklist-render.json
      sideboard-plans.json
      slide-plans.json
      layout.json
      sources/
      references/
      cards/
    <Matchup Name>/
      generated matchup images
```

Use one matchup subfolder for each matchup. When an image supports a specific matchup, keep it in that matchup folder even if the source plan type is a slide or follow-up.

## Source Of Truth
- Deck-specific configs live in `output/<Deck Name>/Data/`.
- Shared official card cache data is local-only and ignored by git. Regenerate it with `Tools/scripts/sync_official_riftbound_assets.py`.
- Reusable templates live in `Data/templates/`.
- `Data/render-manifest.json` is the manifest of historical finalized outputs to regenerate and compare.

## Rules
- Source/reference assets that are needed for deterministic rendering may live under the deck's `Data/` folder, but raw card images and card-cache files must stay local-only.
- Use explicit `output_path` fields in plans so generated images land in the new `output/<Deck Name>/...` structure.
- Preserve existing generated images by rendering new files into their destination paths, not by moving references forward.
- Run the manifest regeneration after structural or renderer changes.
