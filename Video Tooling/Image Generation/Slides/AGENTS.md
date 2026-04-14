# Slides Workflow

## Goal
Create polished talking-point slides and follow-up card-overlay slides while keeping slide-specific references, plans, and exports separate from decklist-annotation assets.

## Recommended Folder Structure
- `Set <N>/<Deck Name>/References/`: visual references or source slides you want to match.
- `Set <N>/<Deck Name>/Slides/`: final rendered slide exports.
- `Set <N>/<Deck Name>/slide-plans.json`: the source of truth for informative and follow-up slide plans for that deck.

## Slide Types
1. `informative`: title, bullets, optional left-column cards, and either a patterned or faded-image background.
2. `follow_up`: a blurred base slide with explicit card renders added on top.
3. `follow_up` with `card_layout: { "mode": "featured_center" }`: a single centered hero card over a blurred decklist or reference image.

## Process
1. Confirm the deck, slide type, title, and output name.
2. For informative slides, confirm the bullets plus whether the background should be patterned or based on a specific image.
3. For follow-up slides, confirm the exact base slide and exact cards to place on top.
4. Use official Riot card assets only. Prefer direct Riot asset URLs or a local catalog exported from Riot data.
5. Save the plan in `slide-plans.json` and render it through `scripts/generate_slide.py`.

## Visual Preferences
- Informative slides should favor the Irelia foreground treatment: bold title, clean bullets, and zero to two featured cards on the left.
- Informative slide backgrounds can use either a subtle patterned treatment similar to the Kai'sa example or a faded decklist/source image.
- Follow-up slides should blur the supplied base slide and add explicit card renders on top.
- Hero-card follow-up slides should keep the card centered and upright unless the request explicitly asks for a different angle.
- Do not hallucinate card art or decklist backgrounds. Use a specified official image or prompt for one when the request leaves it ambiguous.

## Tooling Preference
- Use `scripts/generate_slide.py` for repeatable slide generation.
- Keep shared asset-resolution and rendering helpers in `Image Generation/_shared/` rather than duplicating them here.
- Slide plans should be stored separately from `sideboard-plans.json` when possible to keep the workflows decoupled.
