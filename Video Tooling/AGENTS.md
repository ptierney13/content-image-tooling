# Riftbound Video Tooling

## Supported Processes
- `Decklist Images`: create and update matchup sideboarding guide images from exported decklist screenshots.
- `Decklist Posters`: render original decklist poster images from plaintext decklists plus official Riftbound card assets.
- `Talking Point Slides`: render informative matchup slides with bullets and optional supporting cards.
- `Feature Slides`: blur an existing slide or source image and center one official card render on top.
- `Follow-Up Slides`: blur an existing slide and place one or more explicit card overlays on top.

## Project Layout
- `Image Generation/`: image-based workflows and assets.
- `Image Generation/Decklist Images/`: decklist-specific tooling, process docs, and per-set deck image assets.
- `Image Generation/Slides/`: slide-specific tooling, process docs, and slide asset guidance.
- `Image Generation/_card_cache/`: shared official card catalogs and cached card renders reused across image workflows.
- `Image Generation/_shared/`: shared rendering helpers used by both workflows.

## Where To Start
- If the request is about sideboard marks, matchup swap overlays, or annotating a maindeck export, start in `Image Generation/Decklist Images/`.
- If the request is about rendering a fresh decklist image from deck text plus official card assets, start in `Image Generation/Decklist Images/`.
- If the request is about matchup-summary slides, start in `Image Generation/Slides/`.
- If the request is about overlaying one card on top of a blurred existing slide or source image, treat it as a `Feature Slide` in `Image Generation/Slides/`.
- If the request is about overlaying multiple cards on top of a blurred existing slide, treat it as a `Follow-Up Slide` in `Image Generation/Slides/`.
- If the request needs renderer changes that affect both workflows, inspect `Image Generation/_shared/` after reading the nearest workflow `AGENTS.md`.

## Source Of Truth By Workflow
- `Image Generation/Decklist Images/Set <N>/<Deck Name>/Maindeck/`: canonical untouched deck export screenshots.
- `Image Generation/Decklist Images/Set <N>/<Deck Name>/sideboard-plans.json`: source of truth for matchup annotation plans.
- `Image Generation/Slides/Set <N>/<Deck Name>/slide-plans.json`: source of truth for informative slides, feature slides, and follow-up slides.
- `Image Generation/Slides/Set <N>/<Deck Name>/References/`: source slides and other blurred-background inputs for slide plans.
- `Image Generation/Slides/Set <N>/<Deck Name>/Cards/`: official card renders used in feature and follow-up slide overlays.
- `Image Generation/Slides/Set <N>/<Deck Name>/Slides/`: rendered informative slide outputs.
- `Image Generation/Slides/Set <N>/<Deck Name>/Features/`: rendered feature-slide outputs named `<source-slide>-featuring-<card-name>.png`.

## Workflow Rules
- Read the nearest `AGENTS.md` before editing anything inside a workflow folder.
- Keep original maindeck exports, reference guides, deck metadata, and finished matchup images inside the deck's own folder.
- Prefer repeatable tooling over one-off manual edits when a task is likely to recur.
- Save new outputs non-destructively. Keep the original source image untouched and write matchup guides as separate files.
- For deck sideboarding data, keep a single deck-level `sideboard-plans.json` and grow that file as matchup plans change.
- For original decklist poster renders, keep a dedicated deck-level config file such as `decklist-render.json`.
- Use official local or imported card assets for slide overlays. Do not hand-build card composites or pull art from the wrong game/source.
- For decklist poster renders, use official Riftbound card assets only. Do not use third-party-hosted card art or generated card imagery.
- Prefer `Image Generation/scripts/sync_official_riftbound_assets.py` plus the shared `Image Generation/_card_cache/riftbound-official/` cache when a deck render needs official card images fetched from the live Riftbound site.
- Feature slides should be rendered through the Slides workflow as `type: "feature"` plans, not as manual composites.
- Default feature-slide naming should follow `<source-slide>-featuring-<card-name>.png`.

## Workflow Selection Notes
- `Decklist Images` owns screenshot annotation workflows and should be the first place to look for maindeck exports, layout metadata, and matchup swap plans.
- `Slides` owns presentation-style outputs, including informative slides, feature slides, and multi-card follow-up overlays.
- `Feature Slides` should use a source image from `References/`, an official card asset from `Cards/`, and output to `Features/` with the standard `<source-slide>-featuring-<card-name>.png` filename.
- `_shared` should contain reusable rendering logic only; do not store deck-specific plans there.

## Current Baseline
- The first implemented workflow is sideboarding guide image generation for decklist screenshots.
- The deck workflow now also supports high-resolution poster-style decklist renders from plaintext decklists and official card assets.
- Slide generation now lives in its own workflow folder with shared helpers under `Image Generation/_shared/`.
- Single-card blurred-background overlays now live as first-class `feature` slide plans.
- The default annotation style is the polished solid-color look used by the Ezreal Tempo Irelia guide.
- Follow the nearest workflow `AGENTS.md` for storage, annotation style, and output naming.
