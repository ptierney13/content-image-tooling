# Decklist Images Workflow

## Goal
Create polished deck-focused images while keeping a clean per-deck archive of sources, references, metadata, and finished outputs.

This workflow now covers:

- sideboarding guide images built on top of canonical decklist screenshots
- original decklist poster images rendered from plaintext decklists plus official Riftbound card assets

## Required Folder Structure
- `Set <N>/<Deck Name>/Maindeck/`: untouched source decklist exports for that deck.
- `Set <N>/<Deck Name>/References/`: examples or matchup-guide references used for visual direction.
- `Set <N>/<Deck Name>/Sideboard Guides/`: final matchup-specific guide images.
- `Set <N>/<Deck Name>/Deck Images/`: final rendered decklist poster images.
- `Image Generation/_card_cache/riftbound-official/`: shared official catalog plus cached official Riftbound card images reused across decks and slides.
- `Set <N>/<Deck Name>/layout.json`: coordinate metadata used by the generator to place annotations on the correct cards.
- `Set <N>/<Deck Name>/sideboard-plans.json`: the single source of truth for every sideboard plan for that deck.
- `Set <N>/<Deck Name>/decklist-render.json` or similar: source of truth for one or more original decklist poster plans.
- `Set <N>/<Deck Name>/decklist.txt`: optional plaintext decklist source file when you do not want to inline the decklist in JSON.

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

## Decklist Poster Process
1. Stop and confirm the deck title, set, and the exact plaintext decklist. Never infer the deck title from the Legend, file name, folder name, or plan key.
2. Confirm where official Riftbound card assets will come from:
   - the shared official cache built by `scripts/sync_official_riftbound_assets.py`
   - an official exported catalog with `assets[].gameAbsolutePath`
   - explicit `official_image_url` / `riot_image_url`
   - local cached official card exports referenced via `local_path`
3. Stop and ask which battlefield is `Play`, `Draw`, and `Game 1` if any `Battlefields:` entry does not already include a label after `|`.
4. Save the decklist text beside the deck assets or inline it in the config.
5. Save the poster plan in `decklist-render.json` (or another dedicated config file).
6. Run `scripts/sync_official_riftbound_assets.py --decklist-file "<decklist.txt>"` when the shared official cache needs new cards.
7. Render through `scripts/generate_decklist_image.py`.
8. Review the output for readability, card sizing, and whether the composition feels original rather than copied from a third-party branded template.
9. The `Runes:` entry order is not significant. The renderer crops symbols from the official Legend art using normalized positions, displays them in Legend-card order, and pairs counts to the matching rune names.

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
- For original decklist posters, keep the overall feel dark and polished but use an original background treatment, typography, and framing so the render is not a close copy of a third-party branded layout.
- Do not reproduce another creator's branding, QR treatment, watermark, or signature ornamental patterning.
- Card imagery must always come from official Riftbound sources or cached official exports. Never fabricate card art.
- Rune symbols must come from the official Legend card image when possible. Do not draw, generate, or substitute unofficial rune icons.
- It is fine to use text pills or labels for metadata such as runes if no official visual asset is being placed there.

## Tooling Preference
- Use `scripts/generate_decklist_image.py` for repeatable image generation.
- `scripts/generate_sideboard_guide.py` remains available as a compatibility wrapper for older commands.
- Keep deck-specific geometry in `layout.json` instead of hardcoding every future matchup directly in the script.
- The generator should read one `sideboard-plans.json` file per deck and support regenerating either one plan or every stored plan in that file.
- Decklist poster plans should live in a dedicated config file rather than being mixed into `sideboard-plans.json`.
- Decklist poster plans must include an explicit `deck_name` or `title`.
- Battlefield decklist entries must include explicit labels such as `1 Marai Spire | Game 1`; never assume labels from list order.
- Prefer official catalog-backed image resolution over ad hoc URLs for decklist poster renders.
- Prefer the shared `_card_cache/riftbound-official/` catalog and image cache over deck-local card caches so new decks automatically reuse already-fetched official images.
- When tuning rune crops, update the shared normalized crop constants once in `_shared/render_image_plans.py` instead of creating per-deck rune image assets.
- Use `scripts/verify_x_alignment.py` when you need to visually confirm `X` centering across several cards before finalizing a guide.
