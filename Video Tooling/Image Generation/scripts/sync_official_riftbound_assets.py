import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


IMAGE_GENERATION_DIR = Path(__file__).resolve().parents[1]
SHARED_DIR = IMAGE_GENERATION_DIR / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import render_image_plans as rip


DEFAULT_LOCALE = "en-us"
DEFAULT_OUTPUT_DIR = IMAGE_GENERATION_DIR / "_card_cache" / "riftbound-official"
CARD_GALLERY_URL = "https://riftbound.leagueoflegends.com/{locale}/card-gallery/"
CARD_GALLERY_JSON_URL = "https://riftbound.leagueoflegends.com/_next/data/{build_id}/{locale}/card-gallery.json"
USER_AGENT = "RiftboundImageGeneration/1.0"
RARITY_RANK = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "showcase": -1,
}
LEGEND_TYPE_ID = "legend"


def _read_url_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Request failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc


def _read_url_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=60) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Request failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc


def _extract_build_id(html: str) -> str:
    match = re.search(r'"buildId":"(?P<build>[^"]+)"', html)
    if not match:
        raise ValueError("Unable to find the Riftbound card gallery buildId in the page HTML.")
    return match.group("build")


def _load_gallery_payload(locale: str) -> tuple[dict, dict]:
    page_url = CARD_GALLERY_URL.format(locale=locale)
    html = _read_url_text(page_url)
    build_id = _extract_build_id(html)
    json_url = CARD_GALLERY_JSON_URL.format(build_id=build_id, locale=locale)
    payload = json.loads(_read_url_text(json_url))
    return payload, {
        "page_url": page_url,
        "json_url": json_url,
        "build_id": build_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _gallery_cards(payload: dict) -> list[dict]:
    blades = payload.get("pageProps", {}).get("page", {}).get("blades", [])
    for blade in blades:
        if blade.get("type") == "riftboundCardGallery":
            return list(blade.get("cards", {}).get("items", []))
    raise ValueError("Unable to locate the Riftbound card gallery card list in the official payload.")


def _is_showcase_variant(card: dict) -> bool:
    rarity_id = card.get("rarity", {}).get("value", {}).get("id")
    return rarity_id == "showcase"


def _variant_score(card: dict) -> tuple[int, int, int, int]:
    rarity_id = card.get("rarity", {}).get("value", {}).get("id", "")
    image_width = int(card.get("cardImage", {}).get("dimensions", {}).get("width", 0))
    image_height = int(card.get("cardImage", {}).get("dimensions", {}).get("height", 0))
    public_code = str(card.get("publicCode", ""))
    has_special_suffix = 1 if ("*" in public_code or re.search(r"[a-z]/", public_code.lower())) else 0
    return (
        RARITY_RANK.get(rarity_id, -2),
        0 if _is_showcase_variant(card) else 1,
        0 if has_special_suffix else 1,
        image_width * image_height,
    )


def _preferred_records(cards: list[dict], images_dir: Path) -> list[dict]:
    records_by_name: dict[str, list[dict]] = {}
    for card in cards:
        card_image = card.get("cardImage", {})
        if not isinstance(card_image, dict) or not card_image.get("url"):
            continue
        records_by_name.setdefault(card["name"], []).append(card)

    normalized_records = []
    for name, candidates in records_by_name.items():
        selected = max(candidates, key=_variant_score)
        public_code = str(selected.get("publicCode", selected.get("id", name)))
        suffix = Path(urlparse(selected["cardImage"]["url"]).path).suffix or ".png"
        filename = f"{rip._filename_slug(public_code.replace('/', '-').replace('*', '-star'))}-{rip._filename_slug(name)}{suffix}"
        local_path = (images_dir / filename).resolve()
        record = {
            "name": name,
            "cardCode": public_code,
            "publicCode": public_code,
            "setId": selected.get("set", {}).get("value", {}).get("id"),
            "setLabel": selected.get("set", {}).get("value", {}).get("label"),
            "orientation": selected.get("orientation"),
            "rarity": selected.get("rarity", {}).get("value", {}).get("id"),
            "cardType": [entry.get("id") for entry in selected.get("cardType", {}).get("type", []) if isinstance(entry, dict)],
            "cardSuperType": [entry.get("id") for entry in selected.get("cardType", {}).get("superType", []) if isinstance(entry, dict)],
            "official_image_url": selected["cardImage"]["url"],
            "image_dimensions": [
                int(selected.get("cardImage", {}).get("dimensions", {}).get("width", 0)),
                int(selected.get("cardImage", {}).get("dimensions", {}).get("height", 0)),
            ],
            "accessibilityText": selected.get("cardImage", {}).get("accessibilityText"),
        }
        aliases = _record_aliases(selected)
        if aliases:
            record["aliases"] = aliases
        if local_path.exists():
            record["local_path"] = str(local_path)
        normalized_records.append(record)

    normalized_records.sort(key=lambda record: (record["name"].lower(), record.get("publicCode", "")))
    return normalized_records


def _record_aliases(card: dict) -> list[str]:
    card_type_ids = [entry.get("id") for entry in card.get("cardType", {}).get("type", []) if isinstance(entry, dict)]
    if LEGEND_TYPE_ID not in card_type_ids:
        return []

    name = str(card.get("name", ""))
    if "," in name:
        return []

    tags = [str(tag).strip() for tag in card.get("tags", {}).get("tags", []) if str(tag).strip()]
    if not tags:
        return []

    owner_name = tags[0]
    if not owner_name or owner_name.lower() == name.lower():
        return []
    return [f"{owner_name}, {name}"]


def _selected_card_names(decklist_file: Path | None, explicit_cards: list[str]) -> list[str]:
    selected_names: list[str] = []
    if decklist_file:
        deck_data = rip._parse_decklist_text(decklist_file.read_text(encoding="utf-8-sig"))
        for key in ("legend", "champion", "maindeck", "battlefields", "runes", "sideboard"):
            section = deck_data["by_key"].get(key)
            if not section:
                continue
            selected_names.extend(entry["card_name"] for entry in section["entries"])

    selected_names.extend(explicit_cards)
    seen: set[str] = set()
    ordered_names: list[str] = []
    for name in selected_names:
        slug = rip._slug(name)
        if slug in seen:
            continue
        seen.add(slug)
        ordered_names.append(name)
    return ordered_names


def _records_by_slug(records: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for record in records:
        indexed[rip._slug(record["name"])] = record
        for alias in record.get("aliases", []):
            indexed.setdefault(rip._slug(alias), record)
    return indexed


def _download_record_image(record: dict, images_dir: Path) -> Path:
    public_code = str(record.get("publicCode", record["name"]))
    suffix = Path(urlparse(record["official_image_url"]).path).suffix or ".png"
    filename = f"{rip._filename_slug(public_code.replace('/', '-').replace('*', '-star'))}-{rip._filename_slug(record['name'])}{suffix}"
    destination = (images_dir / filename).resolve()
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_read_url_bytes(record["official_image_url"]))
    return destination


def _prefetch_selected_records(records: list[dict], selected_names: list[str], images_dir: Path) -> None:
    if not selected_names:
        return

    by_slug = _records_by_slug(records)
    missing = [name for name in selected_names if rip._slug(name) not in by_slug]
    if missing:
        raise ValueError(f"Unable to locate the following official Riftbound cards: {', '.join(missing)}")

    for name in selected_names:
        record = by_slug[rip._slug(name)]
        record["local_path"] = str(_download_record_image(record, images_dir))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the official Riftbound card gallery into a shared local catalog and cache selected card images.")
    parser.add_argument("--locale", default=DEFAULT_LOCALE, help="Locale to fetch from the official Riftbound card gallery. Default: en-us")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Shared cache directory for the normalized catalog and downloaded images. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument("--decklist-file", help="Optional plaintext decklist file. If provided, the script downloads the official images for every non-rune card in that list.")
    parser.add_argument("--card", action="append", default=[], help="Optional card name to prefetch. Can be provided multiple times.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    images_dir = output_dir / "images"
    catalog_path = output_dir / f"catalog-{args.locale}.json"
    metadata_path = output_dir / f"metadata-{args.locale}.json"

    payload, metadata = _load_gallery_payload(args.locale)
    records = _preferred_records(_gallery_cards(payload), images_dir)
    selected_names = _selected_card_names(Path(args.decklist_file).resolve() if args.decklist_file else None, list(args.card))
    _prefetch_selected_records(records, selected_names, images_dir)

    _write_json(catalog_path, records)
    _write_json(
        metadata_path,
        {
            **metadata,
            "locale": args.locale,
            "catalog_path": str(catalog_path),
            "images_dir": str(images_dir),
            "downloaded_cards": selected_names,
            "record_count": len(records),
        },
    )

    print(f"Wrote official catalog: {catalog_path}")
    print(f"Wrote official metadata: {metadata_path}")
    if selected_names:
        print(f"Cached {len(selected_names)} official card image(s) in {images_dir}")
    else:
        print("No card images were prefetched; catalog only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
