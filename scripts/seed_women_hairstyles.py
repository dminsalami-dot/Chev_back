import argparse
import base64
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Set

from google import genai
from openai import OpenAI
from tqdm import tqdm

# Add src to pythonpath so imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chevstyle_backend.config import settings
from chevstyle_backend.convex.client import ConvexClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("seed_women_hairstyles")

ALLOWED_CATEGORIES = ["curly", "fade", "short", "long", "locs"]

VISION_PROMPT = f"""You are an expert hair stylist and beauty catalog taxonomist.
Analyze the provided image of a woman's hairstyle and extract detailed, structured metadata for a virtual hairstyle try-on catalog.

### Rules & Allowed Values
1. "name": A concise, stylish, and professional name for the haircut/hairstyle (e.g. "Sleek Blunt Cut Bob", "Honey Blonde Passion Twists", "Defined Bouncy Spiral Curls", "Textured Pixie with Low Fade").
2. "gender": Must always be "women".
3. "categories": A JSON array of applicable tags ONLY from this exact allowed list: {json.dumps(ALLOWED_CATEGORIES)}.
   - Pick between 1 and 3 categories that accurately describe the hairstyle in the photo (e.g. ["curly", "long"], ["short", "fade"], ["locs", "long"], ["short"]).
   - Do NOT include any categories outside of this list.
4. "description": 2-3 engaging sentences describing the aesthetic, texture, silhouette, and vibe of the hairstyle.
5. "maintenanceLevel": Must be exactly one of: "Low", "Medium", or "High".
6. "stylistSpecs": Clear, actionable, technical styling & cutting specs for a professional stylist or barber (cutting technique, clipper/scissor work, parting, texturizing, styling products, and drying/finishing method).
7. "hashtags": A list of 3-5 consistent lowercase hashtags with "#" (e.g. ["#curlyhair", "#longcurls", "#womenshair", "#naturalhair"]).
8. "likesCount": "0".
9. "isTrending": boolean (true or false).

### Output Format
Return ONLY valid JSON matching this exact structure:
{{
  "name": "...",
  "gender": "women",
  "categories": ["..."],
  "description": "...",
  "maintenanceLevel": "...",
  "stylistSpecs": "...",
  "hashtags": ["#..."],
  "likesCount": "0",
  "isTrending": true
}}
"""


def compute_image_hash(image_bytes: bytes) -> str:
    """Computes a SHA-256 hash of the raw image bytes to serve as a unique pictureHash."""
    return hashlib.sha256(image_bytes).hexdigest()


def sanitize_metadata(data: dict) -> dict:
    """Cleans and validates the parsed JSON dictionary to match schema requirements."""
    raw_cats = data.get("categories", [])
    valid_cats = [c.lower() for c in raw_cats if c.lower() in ALLOWED_CATEGORIES]
    if not valid_cats:
        valid_cats = ["short"]
    data["categories"] = valid_cats
    data["likesCount"] = "0"
    data["gender"] = "women"

    if data.get("maintenanceLevel") not in ("Low", "Medium", "High"):
        data["maintenanceLevel"] = "Medium"

    if not isinstance(data.get("hashtags"), list):
        data["hashtags"] = ["#womenshair", "#hairstyles", "#naturalhair"]

    if not isinstance(data.get("isTrending"), bool):
        data["isTrending"] = False

    return data


def parse_json_response(content: str) -> dict:
    """Strips markdown wrappers and parses JSON."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:].rstrip("`").strip()
    elif content.startswith("```"):
        content = content[3:].rstrip("`").strip()
    return json.loads(content)


def extract_metadata_from_gemini(
    client: genai.Client, image_bytes: bytes, mime_type: str, max_retries: int = 3
) -> dict[str, Any]:
    """Calls Gemini Vision to extract structured hairstyle metadata."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    for attempt in range(max_retries):
        try:
            interaction = client.interactions.create(
                model="gemini-3.6-flash",
                input=[
                    {
                        "type": "image",
                        "data": image_b64,
                        "mime_type": mime_type,
                    },
                    {
                        "type": "text",
                        "text": VISION_PROMPT,
                    },
                ],
            )

            raw_text = getattr(interaction, "output_text", None)
            if not raw_text:
                raise ValueError("Gemini returned empty text response or safety filter blocked output.")

            data = parse_json_response(raw_text)
            return sanitize_metadata(data)

        except Exception as exc:
            exc_str = str(exc)
            match = re.search(r"retry in ([\d\.]+)s", exc_str)
            if match:
                delay = float(match.group(1)) + random.uniform(1.0, 3.0)
            elif "429" in exc_str or "quota" in exc_str.lower() or "resource_exhausted" in exc_str.lower():
                delay = 15.0 + (attempt * 10.0) + random.uniform(1.0, 3.0)
            else:
                delay = 3.0 * (attempt + 1) + random.uniform(0.5, 2.0)

            logger.warning(
                f"[Gemini] Attempt {attempt + 1}/{max_retries} failed: {exc_str[:100]}. Waiting {delay:.1f}s..."
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise exc


def extract_metadata_from_openai(
    client: OpenAI, image_bytes: bytes, mime_type: str, model: str = "gpt-4o"
) -> dict[str, Any]:
    """Calls OpenAI Vision as a high-reliability fallback."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:{mime_type};base64,{image_b64}"

    logger.info(f"[OpenAI] Calling {model} for image metadata...")

    # First attempt: Responses API if requested or Chat Completions API
    try:
        if hasattr(client, "responses") and model.startswith("gpt-5"):
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": VISION_PROMPT},
                            {"type": "input_image", "image_url": data_uri},
                        ],
                    }
                ],
            )
            raw_text = getattr(response, "output_text", None) or str(response)
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                temperature=0.2,
            )
            raw_text = response.choices[0].message.content

        if not raw_text:
            raise ValueError("OpenAI returned an empty response.")

        data = parse_json_response(raw_text)
        return sanitize_metadata(data)

    except Exception as exc:
        logger.error(f"[OpenAI] Error calling {model}: {exc}")
        # If specific model failed, fallback to gpt-4o or gpt-4o-mini
        if model != "gpt-4o-mini" and model != "gpt-4o":
            logger.info("[OpenAI] Retrying with gpt-4o fallback...")
            return extract_metadata_from_openai(client, image_bytes, mime_type, model="gpt-4o")
        raise exc


def extract_metadata(
    image_bytes: bytes,
    mime_type: str,
    openai_client: Optional[OpenAI],
    gemini_client: Optional[genai.Client],
    openai_model: str = "gpt-4o",
    primary_provider: str = "openai",
) -> dict[str, Any]:
    """Tries the primary provider (default OpenAI); falls back to secondary if it fails."""
    if primary_provider == "openai":
        if openai_client:
            try:
                return extract_metadata_from_openai(openai_client, image_bytes, mime_type, model=openai_model)
            except Exception as exc:
                if gemini_client:
                    logger.warning(
                        f"OpenAI failed ({exc.__class__.__name__}: {str(exc)[:100]}). Falling back to Gemini..."
                    )
                    return extract_metadata_from_gemini(gemini_client, image_bytes, mime_type)
                raise exc
        elif gemini_client:
            return extract_metadata_from_gemini(gemini_client, image_bytes, mime_type)
    else:
        if gemini_client:
            try:
                return extract_metadata_from_gemini(gemini_client, image_bytes, mime_type)
            except Exception as exc:
                if openai_client:
                    logger.warning(
                        f"Gemini failed ({exc.__class__.__name__}: {str(exc)[:100]}). Falling back to OpenAI ({openai_model})..."
                    )
                    return extract_metadata_from_openai(openai_client, image_bytes, mime_type, model=openai_model)
                raise exc
        elif openai_client:
            return extract_metadata_from_openai(openai_client, image_bytes, mime_type, model=openai_model)

    raise RuntimeError("No AI provider (OpenAI or Gemini) configured with a valid API key.")


def get_mime_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    elif lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def process_image(
    file_path: Path,
    openai_client: Optional[OpenAI],
    gemini_client: Optional[genai.Client],
    convex_client: ConvexClient,
    openai_model: str = "gpt-4o",
    primary_provider: str = "openai",
    dry_run: bool = False,
) -> dict[str, Any]:
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    mime_type = get_mime_type(file_path.name)
    picture_hash = compute_image_hash(file_bytes)

    # 1. Vision AI Metadata (OpenAI primary, Gemini fallback)
    metadata = extract_metadata(
        image_bytes=file_bytes,
        mime_type=mime_type,
        openai_client=openai_client,
        gemini_client=gemini_client,
        openai_model=openai_model,
        primary_provider=primary_provider,
    )

    if dry_run:
        image_url = f"https://mock.cdn.convex.dev/img/{file_path.stem}.jpg"
        return {
            "source_file": file_path.name,
            "id": f"dry_run_{file_path.stem}",
            "name": metadata["name"],
            "gender": "women",
            "categories": metadata["categories"],
            "imageUrl": image_url,
            "pictureHash": picture_hash,
            "description": metadata["description"],
            "maintenanceLevel": metadata["maintenanceLevel"],
            "stylistSpecs": metadata["stylistSpecs"],
            "hashtags": metadata["hashtags"],
            "likesCount": "0",
            "isTrending": metadata.get("isTrending", False),
        }

    # 2. Store Image in Convex Storage
    storage_id = convex_client.store_image(file_bytes, mime_type=mime_type)
    image_url = convex_client.get_storage_url(storage_id)

    # 3. Insert into Convex Hairstyles Table
    record = convex_client.create_hairstyle(
        name=metadata["name"],
        gender="women",
        categories=metadata["categories"],
        image_url=image_url,
        picture_hash=picture_hash,
        description=metadata["description"],
        maintenance_level=metadata["maintenanceLevel"],
        stylist_specs=metadata["stylistSpecs"],
        hashtags=metadata["hashtags"],
        likes_count="0",
        is_trending=metadata.get("isTrending", False),
    )
    record["source_file"] = file_path.name
    record["pictureHash"] = picture_hash
    return record


def inspect_convex_duplicates(convex_client: ConvexClient) -> None:
    """Queries Convex and reports any duplicate hairstyles detected in the database."""
    try:
        hairstyles = convex_client.list_hairstyles("women")
    except Exception as exc:
        logger.error(f"Failed to fetch hairstyles from Convex: {exc}")
        return

    logger.info(f"Analyzing {len(hairstyles)} hairstyles in Convex for duplicates...")

    by_hash: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}

    for h in hairstyles:
        h_hash = h.get("pictureHash")
        if h_hash:
            by_hash.setdefault(h_hash, []).append(h)
        h_name = (h.get("name") or "").strip().lower()
        if h_name:
            by_name.setdefault(h_name, []).append(h)

    dup_hashes = {k: v for k, v in by_hash.items() if len(v) > 1}
    dup_names = {k: v for k, v in by_name.items() if len(v) > 1}

    if not dup_hashes and not dup_names:
        logger.info("No duplicates found in Convex database.")
        return

    logger.warning(f"Found {len(dup_hashes)} duplicate picture hashes and {len(dup_names)} duplicate style names:")
    for name, items in dup_names.items():
        ids = [item.get("_id") or item.get("id") for item in items]
        logger.warning(f"  - Name '{name}' appears {len(items)} times with IDs: {ids}")


def main():
    parser = argparse.ArgumentParser(
        description="Seed women's hairstyles into Convex with Vision AI metadata (Gemini + OpenAI Fallback)"
    )
    parser.add_argument(
        "--dir",
        type=str,
        default="src/chevstyle_backend/women",
        help="Directory containing the hairstyle images",
    )
    parser.add_argument(
        "--single",
        type=str,
        default=None,
        help="Process only a single specific image filename",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract metadata and print JSON without uploading to Convex",
    )
    parser.add_argument(
        "--export-json",
        type=str,
        default="women_hairstyles_backup.json",
        help="Path to export all generated records to a local JSON file (progressively saved)",
    )
    parser.add_argument(
        "--primary-provider",
        type=str,
        default="openai",
        choices=["openai", "gemini"],
        help="Primary AI Vision provider (default: openai)",
    )
    parser.add_argument(
        "--openai-model",
        type=str,
        default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay in seconds between processing images (default: 1.5s)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip images that are already present in the export JSON file or Convex DB",
    )
    parser.add_argument(
        "--check-convex-duplicates",
        action="store_true",
        help="Inspect and report duplicate hairstyles currently in Convex DB and exit",
    )
    args = parser.parse_args()

    convex_client = ConvexClient()

    if args.check_convex_duplicates:
        inspect_convex_duplicates(convex_client)
        return

    images_dir = Path(args.dir)
    if not images_dir.exists():
        logger.error(f"Directory not found: {images_dir}")
        sys.exit(1)

    all_files = sorted([
        f for f in images_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    ])

    if args.single:
        target_files = [f for f in all_files if f.name == args.single or f.stem == args.single]
        if not target_files:
            logger.error(f"File '{args.single}' not found in {images_dir}")
            sys.exit(1)
    else:
        target_files = all_files

    # Initialize AI Clients
    openai_client = OpenAI(api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY")) if (settings.openai_api_key or os.getenv("OPENAI_API_KEY")) else None
    gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

    if not openai_client and not gemini_client:
        logger.error("Neither OPENAI_API_KEY nor GEMINI_API_KEY is configured.")
        sys.exit(1)

    logger.info(
        f"AI Setup: Primary={args.primary_provider.upper()} (Model: {args.openai_model}), "
        f"OpenAI={'YES' if openai_client else 'NO'}, Gemini={'YES' if gemini_client else 'NO'}"
    )

    # 1. Load existing progress from local backup JSON if available
    export_path = Path(args.export_json) if args.export_json else None
    results: List[dict[str, Any]] = []
    processed_sources: Set[str] = set()
    processed_hashes: Set[str] = set()

    if export_path and export_path.exists():
        try:
            with open(export_path, "r", encoding="utf-8") as f:
                results = json.load(f)
                for r in results:
                    if r.get("source_file"):
                        processed_sources.add(r["source_file"])
                    if r.get("pictureHash"):
                        processed_hashes.add(r["pictureHash"])
            logger.info(f"Loaded {len(results)} previously saved records from {export_path}")
        except Exception as exc:
            logger.warning(f"Could not load existing backup file: {exc}")

    # 2. Query Convex DB directly for existing hairstyles to ensure absolute idempotency
    if not args.dry_run and args.skip_existing:
        try:
            existing_in_db = convex_client.list_hairstyles(gender="women")
            for h in existing_in_db:
                if h.get("pictureHash"):
                    processed_hashes.add(h["pictureHash"])
            logger.info(f"Fetched {len(existing_in_db)} hairstyles from Convex DB for deduplication.")
        except Exception as exc:
            logger.warning(f"Could not query Convex DB for existing records: {exc}")

    # 3. Filter out already processed files by filename AND content hash
    filtered_files = []
    for f in target_files:
        if args.skip_existing:
            if f.name in processed_sources:
                continue
            with open(f, "rb") as img_f:
                file_hash = compute_image_hash(img_f.read())
            if file_hash in processed_hashes:
                continue
        filtered_files.append(f)

    target_files = filtered_files

    if not target_files:
        logger.info("All images have already been processed and exist in Convex. Nothing to seed!")
        return

    logger.info(
        f"Continuing seeding for {len(target_files)} remaining images (Delay: {args.delay}s, Dry run: {args.dry_run})"
    )

    success_count = 0
    fail_count = 0

    progress_bar = tqdm(target_files, desc="Seeding Hairstyles", unit="img", ncols=100)

    for file_path in progress_bar:
        progress_bar.set_postfix({"current": file_path.name[:18]})
        try:
            record = process_image(
                file_path=file_path,
                openai_client=openai_client,
                gemini_client=gemini_client,
                convex_client=convex_client,
                openai_model=args.openai_model,
                primary_provider=args.primary_provider,
                dry_run=args.dry_run,
            )
            results.append(record)
            if record.get("source_file"):
                processed_sources.add(record["source_file"])
            if record.get("pictureHash"):
                processed_hashes.add(record["pictureHash"])

            success_count += 1
            progress_bar.set_postfix({
                "done": success_count,
                "style": record.get("name", "")[:20],
            })

            # Incremental save so no progress is lost if interrupted
            if export_path:
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2)

        except Exception as exc:
            logger.error(f"\nFailed to process {file_path.name}: {exc}")
            fail_count += 1

        if args.delay > 0:
            time.sleep(args.delay)

    progress_bar.close()
    logger.info("========================================")
    logger.info(f"Seeding completed: {success_count} succeeded, {fail_count} failed out of {len(target_files)}")
    if export_path:
        logger.info(f"All {len(results)} records saved to {export_path}")


if __name__ == "__main__":
    main()

