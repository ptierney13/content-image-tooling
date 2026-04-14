# Decklist Images Workflow

## Goal
Create polished sideboarding guide images from decklist screenshots while keeping a clean per-deck archive of sources, references, metadata, and finished outputs.

## Required Folder Structure
- `Set <N>/<Deck Name>/Maindeck/`: untouched source decklist exports for that deck.
- `Set <N>/<Deck Name>/References/`: examples or matchup-guide references used for visual direction.
- `Set <N>/<Deck Name>/Sideboard Guides/`: final matchup-specific guide images.
- `Set <N>/<Deck Name>/layout.json`: coordinate metadata used by the generator to place annotations on the correct cards.
- `Set <N>/<Deck Name>/sideboard-plans.json`: the single source of truth for every sideboard plan for that deck.

## File Discovery Rules
- Find the base image for a guide in the deck folder's `Maindeck/` directory.
- Keep exactly one canonical source export per deck when possible. If variants exist, name them clearly and note which one is canonical in the task.
- Store reusable coordinate metadata in `layout.json` beside the deck assets so future matchup guides can be generated without re-measuring card positions.
- Center `X` markers from the actual `xN` badge text gap when possible, not the raw card box center. Keep optional per-slot metadata in `layout.json` only if the automatic badge-text anchor ever needs an override.
- Store all matchup plans for a deck in `sideboard-plans.json`; add or update entries inside that file instead of creating separate matchup JSON files.

## Sideboarding Guide Process
1. Confirm the deck, set, matchup, and the exact swap instructions.
2. Identify the untouched maindeck image in `Maindeck/`.
3. Update the deck's `sideboard-plans.json` with the matchup entry or changes to an existing entry.
4. Check `References/` for a stylistic model if one exists.
5. Update `layout.json` if the card locations or image dimensions changed.
6. Generate the requested guide, or regenerate all guides if the shared rendering style changed.
7. Review the output for mark placement, readability, and consistency with the preferred style.

## Visual Preferences
- Use the untouched maindeck export as the base.
- Default to the polished solid-color style established by the Ezreal Tempo Irelia guide.
- Use bright red for cards coming out:
  - draw a large `X` when the card should be fully removed.
  - draw a red `-1` when only one copy comes out.
- Use bright green checks for cards coming in.
- Keep marker strokes crisp, thick, and confident rather than sketchy or jittered.
- A subtle soft shadow is fine, but avoid hand-drawn wobble, textured brushes, or multi-pass scribbling unless a deck-specific reference explicitly calls for it.
- Center each mark over the card art/text box so it reads clearly at video resolution.
- Preserve the rest of the image exactly as exported.

## Tooling Preference
- Use `scripts/generate_decklist_image.py` for repeatable image generation.
- `scripts/generate_sideboard_guide.py` remains available as a compatibility wrapper for older commands.
- Keep deck-specific geometry in `layout.json` instead of hardcoding every future matchup directly in the script.
- The generator should read one `sideboard-plans.json` file per deck and support regenerating either one plan or every stored plan in that file.
- Use `scripts/verify_x_alignment.py` when you need to visually confirm `X` centering across several cards before finalizing a guide.
