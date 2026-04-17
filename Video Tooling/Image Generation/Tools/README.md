# Tools

This folder contains the scripts and tests used to regenerate deck guide images.

- `scripts/render_image_plans.py`: shared renderer for decklist posters, sideboard guides, informative slides, feature slides, and follow-up slides.
- `scripts/sync_official_riftbound_assets.py`: rebuilds the local ignored official card cache needed by render plans.
- `scripts/regenerate_manifest.py`: renders every finalized image listed in `../Data/render-manifest.json`.
- `scripts/compare_manifest_outputs.py`: optional helper for manifests that include explicit reference image paths.
- `tests/`: focused renderer and layout tests.
