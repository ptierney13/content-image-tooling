# Slides

This workflow is for talking-point slides and explicit follow-up slides.

Use it to render:

- `informative` slides with a title, bullets, optional left-side cards, and either a patterned or faded-image background
- `follow_up` slides that blur a known base slide and add specific cards on top

## Command

```powershell
python scripts/generate_slide.py "Set 2\Ezreal Tempo\slide-plans.json"
python scripts/generate_slide.py "Set 2\Ezreal Tempo\slide-plans.json" "Irelia Summary"
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
  - `{ "mode": "featured_center" }`
    - a single large centered hero card over the blurred background
    - optional `top_margin`, `bottom_margin`, and `side_margin` values let you tune the framing

Use `featured_center` when you want a decklist or source image blurred behind one exact card render without hand-tuning a box each time.

## Card Sourcing

Cards should come from Riot-provided assets. The renderer supports:

- `riot_image_url` or `image_url` on a card entry
- `card_name` or `card_code` plus `card_assets.catalogs`
- `local_path` for a pre-downloaded official Riot asset that you already cached locally

Catalog entries can be either:

- official-style records with `name`, `cardCode`, and `assets[0].gameAbsolutePath`
- simplified records with `name` plus `image_url`

## Background Suggestions

If an informative slide requests a faded image background or a follow-up slide omits `base_slide`, the script will suggest:

1. the config `base_image` if one exists
2. otherwise the first image it finds in `Maindeck/`
3. otherwise the first image it finds in `References/`
