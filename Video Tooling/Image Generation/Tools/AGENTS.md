# Image Generation Tools

## Command Location
Run commands from `Video Tooling/Image Generation`.

## Standard Regeneration
Use the manifest when rebuilding the known finalized outputs:

```powershell
python Tools\scripts\sync_official_riftbound_assets.py --decklist-file "output\Ezreal Tempo\Data\decklist.txt" --decklist-file "output\Lee Sin Centered\Data\decklist.txt" --card "Void Gate" --card "Unchecked Power" --card "Downwell"
python Tools\scripts\regenerate_manifest.py Data\render-manifest.json
```

Use `Data/render-manifest.json` as the authoritative list of generated outputs. Add a deck or matchup item there before asking agents to regenerate all outputs.
Do not commit `Data/card-cache/` or deck-local raw card images; those are local cache inputs only.

## Targeted Rendering
Render a single deck poster:

```powershell
python Tools\scripts\generate_decklist_image.py "output\Ezreal Tempo\Data\decklist-render.json" "Starter Poster"
```

Render a single sideboard guide:

```powershell
python Tools\scripts\generate_sideboard_guide.py "output\Ezreal Tempo\Data\sideboard-plans.json" "Irelia"
```

Render a single slide:

```powershell
python Tools\scripts\generate_slide.py "output\Ezreal Tempo\Data\slide-plans.json" "Midrange Yi Matchup Summary"
```

## Verification
Run tests after script changes:

```powershell
python -m unittest discover Tools\tests
```

If a one-off comparison is needed, provide a manifest that includes explicit `reference` paths and run `Tools\scripts\compare_manifest_outputs.py` against that manifest.
