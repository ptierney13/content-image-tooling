# Riftbound Video Tooling

## Supported Processes
- `Decklist Images`: create and update matchup sideboarding guide images from exported decklist screenshots.
- `Talking Point Slides`: render informative matchup slides and explicit follow-up card overlays.

## Project Layout
- `Image Generation/`: image-based workflows and assets.
- `Image Generation/Decklist Images/`: decklist-specific tooling, process docs, and per-set deck image assets.
- `Image Generation/Slides/`: slide-specific tooling, process docs, and slide asset guidance.
- `Image Generation/_shared/`: shared rendering helpers used by both workflows.

## Workflow Rules
- Read the nearest `AGENTS.md` before editing anything inside a workflow folder.
- Keep original maindeck exports, reference guides, deck metadata, and finished matchup images inside the deck's own folder.
- Prefer repeatable tooling over one-off manual edits when a task is likely to recur.
- Save new outputs non-destructively. Keep the original source image untouched and write matchup guides as separate files.
- For deck sideboarding data, keep a single deck-level `sideboard-plans.json` and grow that file as matchup plans change.

## Current Baseline
- The first implemented workflow is sideboarding guide image generation for decklist screenshots.
- Slide generation now lives in its own workflow folder with shared helpers under `Image Generation/_shared/`.
- The default annotation style is the polished solid-color look used by the Ezreal Tempo Irelia guide.
- Follow the nearest workflow `AGENTS.md` for storage, annotation style, and output naming.
