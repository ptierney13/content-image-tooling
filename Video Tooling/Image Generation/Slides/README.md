# Slides

This workflow is for talking-point slides, feature slides, and explicit follow-up slides.

Use it to render:

- `informative` slides with a title, bullets, optional left-side cards, and either a patterned or faded-image background
- `feature` slides that blur a known source slide and center one featured card on top
- `follow_up` slides that blur a known base slide and add specific cards on top

## Command

```powershell
python scripts/generate_slide.py "Set 2\Ezreal Tempo\slide-plans.json"
python scripts/generate_slide.py "Set 2\Ezreal Tempo\slide-plans.json" "Irelia Summary"
python scripts/generate_slide.py "Set 2\Ezreal Tempo\slide-plans.json" "Ezreal Tempo Maindeck Featuring Ruin Runner"
```

## Plan File Shape

The cleanest setup is a dedicated `slide-plans.json` file under the Slides workflow, but the script can also read slide-type entries from a broader shared plan file.

```json
{
  "card_assets": {
    "cache_dir": "_card_cache",
    "catalogs": [
      "References/riftbound-card-catalog.json"
    ]
  },
  "plans": {
    "Irelia Summary": {
      "type": "informative",
      "output_dir": "Slides",
      "output_image": "Irelia matchup summary.png",
      "title": "Irelia Matchup Summary",
      "background": {
        "kind": "pattern"
      },
      "cards": [
        { "card_name": "Rebuke" }
      ],
      "bullets": [
        "Fight the points race, get to 6 first",
        "Trade cards early and often",
        "Don't let them keep units in play",
        "Dig for Rebuke"
      ]
    },
    "High Impact Options": {
      "type": "follow_up",
      "output_dir": "Slides",
      "output_image": "High Impact Sideboard Options.png",
      "title": "High Impact Sideboard Options",
      "base_slide": "References/Kai'sa matchup strategy guide.png",
      "cards": [
        { "card_name": "Morbid Return" },
        { "card_name": "Dr. Mundo, Expert" },
        { "card_name": "Possession" }
      ]
    },
    "Kai'sa Matchup Guide Featuring Ruin Runner": {
      "type": "feature",
      "base_slide": "References/kai-sa-matchup-guide.png",
      "cards": [
        { "card_name": "Ruin Runner", "local_path": "Cards/ruin-runner.png" }
      ]
    }
  }
}
```

## Informative Slides

Supported keys:

- `type: "informative"`
- `title`
- `output_image` or `output_path`
- `output_dir`
- `bullets`
- `cards`
- `background.kind`
  - `pattern`
  - `faded_image`
- `background.image`
  - Required for `faded_image` unless you want the script to suggest a usable image interactively.
- `bullet_style`
  - `dot` for the Irelia-style look
  - `diamond` for a Kai'sa-style icon treatment

Informative slides support zero, one, or two featured cards on the left.

## Feature Slides

Use `feature` when you want one centered card over a blurred source image.

Supported keys:

- `type: "feature"`
- `base_slide`
- `cards`
  - exactly one card
- `title`
  - optional; defaults to hidden
- `output_image` or `output_path`
  - optional; defaults to `<source-slide>-featuring-<card-name>.png`
- `output_dir`
  - optional; defaults to `Features`
- `card_layout`
  - optional override when you need custom centered margins

Feature-slide card entries should include `card_name` even when `local_path` is provided so the default filename stays clean and stable.

## Follow-Up Slides

Use `follow_up` only when you already know:

- which slide should be blurred in the background
- which exact cards should be placed on top

Supported keys:

- `type: "follow_up"`
- `title`
- `output_image` or `output_path`
- `output_dir`
- `base_slide`
- `cards`
- `card_layout`
  - `grid`
    - the default auto-grid for one or more cards

## Card Sourcing

Cards should come from Riot-provided assets. The renderer supports:

- `riot_image_url` or `image_url` on a card entry
- `card_name` or `card_code` plus `card_assets.catalogs`
- `local_path` for a pre-downloaded official Riot asset that you already cached locally

Recommended folder split for deck-specific slide assets:

- `References/` for source slides and blurred-background inputs
- `Cards/` for official card renders used in overlays
- `Slides/` for informative slide outputs
- `Features/` for single-card feature-slide outputs

Catalog entries can be either:

- official-style records with `name`, `cardCode`, and `assets[0].gameAbsolutePath`
- simplified records with `name` plus `image_url`

## Background Suggestions

If an informative slide requests a faded image background, or a feature/follow-up slide omits `base_slide`, the script will suggest:

1. the config `base_image` if one exists
2. otherwise the first image it finds in `Maindeck/`
3. otherwise the first image it finds in `References/`
