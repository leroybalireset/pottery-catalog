#!/usr/bin/env python3
"""
Sew House LA — Image Processing & Categorization Pipeline

Workflow:
  1. Drop raw images into pottery_catalog/raw/
  2. Run: python3 categorize.py --auto      (AI categorization, when model ready)
     Or:  python3 categorize.py --manual    (outputs list for audit.html)
  3. Review/adjust categorized images in audited/ folders
  4. Run: python3 categorize.py --build    (generates catalog-data.js)

Folder structure:
  pottery_catalog/
    raw/              ← drop original images here
    audited/
      Pottery/        ← processed & categorized pottery images
      Lighting/       ← processed & categorized lighting images
      Statues/        ← processed & categorized statue images
      Skipped/        ← images to exclude from catalog
      Uncertain/      ← needs manual review
"""

import argparse
import base64
import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

# ===== CONFIG =====
ROOT = Path(__file__).parent.resolve()
RAW_DIR = ROOT / "raw"
AUDITED_DIR = ROOT / "audited"
PROGRESS_FILE = ROOT / "categorized.json"
CATALOG_FILE = ROOT / "catalog-data.js"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
VALID_CATEGORIES = {"Pottery", "Lighting", "Statues"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
CROP_SIZE = 800
JPEG_QUALITY = 92

AI_PROMPT = """Look at this image carefully. Categorize the item into exactly one of these three categories:
- Pottery (vases, pots, bowls, urns, ceramic vessels, planters)
- Lighting (lamps, sconces, pendants, chandeliers, light fixtures, candle holders)
- Statues (sculptures, figurines, totems, abstract forms, decorative figures)

Respond with ONLY the category name, nothing else. If truly uncertain, respond with "Uncertain"."""

# ===== IMAGE PROCESSING =====

def process_image(src_path: Path, dst_path: Path) -> bool:
    """Auto-crop to square center, resize to 800x800, save as JPEG."""
    try:
        # Try to use Pillow first
        try:
            from PIL import Image as PILImage
            img = PILImage.open(src_path)
            img = img.convert("RGB")
            w, h = img.size
            size = min(w, h)
            left = (w - size) // 2
            top = (h - size) // 2
            img = img.crop((left, top, left + size, top + size))
            img = img.resize((CROP_SIZE, CROP_SIZE), PILImage.LANCZOS)
            img.save(dst_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return True
        except ImportError:
            pass

        # Fallback to sips (macOS built-in)
        tmp_path = dst_path.with_suffix(".tmp.jpg")
        result = os.system(
            f'sips -Z {CROP_SIZE} --cropToWidthHeight {CROP_SIZE} {CROP_SIZE} '
            f'--padColor F7F5F2 "{src_path}" --out "{tmp_path}" >/dev/null 2>&1'
        )
        if result == 0 and tmp_path.exists():
            shutil.move(str(tmp_path), str(dst_path))
            return True
        else:
            if tmp_path.exists():
                tmp_path.unlink()
            return False
    except Exception as e:
        print(f"  Error processing {src_path.name}: {e}")
        return False


def encode_image_b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def file_to_base64_dataurl(path: Path) -> str:
    ext = path.suffix.lower()
    mime = "image/jpeg"
    if ext == ".png":
        mime = "image/png"
    elif ext == ".webp":
        mime = "image/webp"
    elif ext == ".gif":
        mime = "image/gif"
    return f"data:{mime};base64,{encode_image_b64(path)}"


# ===== AI CATEGORIZATION =====

def check_ollama_model(model: str, host: str) -> bool:
    try:
        resp = requests.get(urljoin(host, "/api/tags"), timeout=10)
        resp.raise_for_status()
        models = {m["name"] for m in resp.json().get("models", [])}
        return model in models or f"{model}:latest" in models
    except Exception:
        return False


def ai_categorize(image_path: Path, model: str, host: str, timeout: int = 120) -> dict:
    """Send image to Ollama vision model and return category."""
    b64 = encode_image_b64(image_path)
    url = urljoin(host, "/api/generate")
    payload = {
        "model": model,
        "prompt": AI_PROMPT,
        "images": [b64],
        "stream": False,
    }
    start = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("response", "").strip()
        elapsed = time.time() - start

        cat = "Uncertain"
        for valid in VALID_CATEGORIES:
            if valid.lower() in raw.lower():
                cat = valid
                break
        if "uncertain" in raw.lower():
            cat = "Uncertain"

        return {
            "category": cat,
            "raw_response": raw,
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
        }
    except requests.exceptions.Timeout:
        return {"category": "Error", "raw_response": "Timeout", "elapsed_seconds": timeout, "error": "Timeout"}
    except Exception as e:
        return {"category": "Error", "raw_response": str(e), "elapsed_seconds": round(time.time() - start, 2), "error": str(e)}


# ===== PROGRESS TRACKING =====

def load_progress() -> list[dict]:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return []


def save_progress(results: list[dict]):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(results, f, indent=2)


def find_raw_images() -> list[Path]:
    if not RAW_DIR.exists():
        return []
    files = []
    for f in sorted(RAW_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
            files.append(f)
    return files


# ===== CATEGORIZATION PIPELINE =====

def run_auto(model: str = "moondream", host: str = OLLAMA_HOST, batch_size: int = 20, timeout: int = 120):
    """Auto-categorize all raw images using local Ollama vision model."""
    images = find_raw_images()
    if not images:
        print(f"No images found in {RAW_DIR}")
        print("Drop your images there first.")
        return

    if not check_ollama_model(model, host):
        print(f"\nModel '{model}' not found in Ollama.")
        print(f"Available: run 'ollama list' to see what's installed.")
        print(f"To download:  ollama pull moondream")
        print(f"Or:           ollama pull llava")
        print(f"Or:           ollama pull llama3.2-vision")
        print(f"\nAlternatively, use --manual mode to categorize with audit.html")
        return

    print(f"Found {len(images)} images in {RAW_DIR}")
    print(f"Model: {model} @ {host}")
    print(f"Batch size: {batch_size}  |  Timeout: {timeout}s")
    print("-" * 50)

    results = load_progress()
    processed_names = {r["filename"] for r in results}
    to_process = [img for img in images if img.name not in processed_names]

    if not to_process:
        print("All images already processed! Use --build to generate catalog-data.js")
        return

    # Ensure audited dirs exist
    for cat in list(VALID_CATEGORIES) + ["Skipped", "Uncertain"]:
        (AUDITED_DIR / cat).mkdir(parents=True, exist_ok=True)

    print(f"Processing {len(to_process)} images...")

    for idx, src_path in enumerate(to_process, 1):
        print(f"[{idx}/{len(to_process)}] {src_path.name} ", end="", flush=True)

        # Process image (crop + resize)
        cat_folder = AUDITED_DIR / "Uncertain"
        dst_path = cat_folder / f"{src_path.stem}.jpg"
        ok = process_image(src_path, dst_path)
        if not ok:
            print("PROCESSING FAILED")
            continue

        # AI categorize
        ai_result = ai_categorize(dst_path, model, host, timeout)
        cat = ai_result["category"]
        elapsed = ai_result["elapsed_seconds"]

        # Move to correct folder
        if cat in VALID_CATEGORIES or cat in {"Skipped", "Uncertain"}:
            new_folder = AUDITED_DIR / cat
            new_path = new_folder / f"{src_path.stem}.jpg"
            if new_path != dst_path:
                shutil.move(str(dst_path), str(new_path))
                dst_path = new_path
        else:
            cat = "Uncertain"

        result = {
            "filename": src_path.name,
            "processed_path": str(dst_path.relative_to(ROOT)),
            "suggested_category": cat,
            "raw_response": ai_result["raw_response"],
            "elapsed_seconds": elapsed,
            "error": ai_result.get("error"),
        }
        results.append(result)
        save_progress(results)
        print(f"→ {cat} ({elapsed}s)")

        # Batch pause
        if idx % batch_size == 0 and idx < len(to_process):
            print(f"\n--- Batch of {batch_size} done. Pausing 3s... ---\n")
            time.sleep(3)

    print_summary(results)
    print(f"\nProgress saved to: {PROGRESS_FILE}")
    print("Review images in audited/ folders. Move any mis-categorized items.")
    print("Then run: python3 categorize.py --build")


def run_manual():
    """Process raw images and copy to Uncertain folder for manual audit."""
    images = find_raw_images()
    if not images:
        print(f"No images found in {RAW_DIR}")
        return

    print(f"Found {len(images)} images in {RAW_DIR}")
    print("Processing (crop + resize)...")

    # Ensure dirs exist
    for cat in list(VALID_CATEGORIES) + ["Skipped", "Uncertain"]:
        (AUDITED_DIR / cat).mkdir(parents=True, exist_ok=True)

    processed = 0
    for src_path in images:
        dst_path = AUDITED_DIR / "Uncertain" / f"{src_path.stem}.jpg"
        if dst_path.exists():
            continue
        ok = process_image(src_path, dst_path)
        if ok:
            processed += 1
            print(f"  ✓ {src_path.name} → {dst_path.relative_to(ROOT)}")
        else:
            print(f"  ✗ {src_path.name} FAILED")

    print(f"\n{processed} images processed and placed in audited/Uncertain/")
    print("\nNext steps:")
    print("  1. Open audit.html in your browser")
    print("  2. Drag images from audited/Uncertain/ into the page, OR")
    print("  3. Manually move images into audited/Pottery/, audited/Lighting/, audited/Statues/")
    print("  4. When done, run: python3 categorize.py --build")


def print_summary(results: list[dict]):
    cats = {}
    errors = 0
    for r in results:
        if r.get("error"):
            errors += 1
        else:
            cats[r["suggested_category"]] = cats.get(r["suggested_category"], 0) + 1

    print("\n" + "=" * 50)
    print("SUMMARY")
    print(f"Total processed: {len(results)}  |  Errors: {errors}")
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count}")


# ===== CATALOG BUILDER =====

def run_build():
    """Generate catalog-data.js from audited/ folders — images as separate files."""

    import shutil

    IMAGES_DIR = ROOT / "images"

    # Collect all image files first
    cat_files = {}
    total = 0
    for category in VALID_CATEGORIES:
        cat_dir = AUDITED_DIR / category
        if not cat_dir.exists():
            continue
        files = sorted([f for f in cat_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS])
        if files:
            cat_files[category] = files
            total += len(files)

    if not total:
        print("No categorized images found in audited/ folders.")
        print("Place processed images into audited/Pottery/, audited/Lighting/, audited/Statues/")
        return

    print(f"Building catalog from {total} images...")

    # Ensure images dir exists and clear old images
    IMAGES_DIR.mkdir(exist_ok=True)
    for cat_dir in IMAGES_DIR.iterdir():
        if cat_dir.is_dir():
            for f in cat_dir.iterdir():
                f.unlink()
    for category in VALID_CATEGORIES:
        (IMAGES_DIR / category).mkdir(exist_ok=True)

    all_items = []
    item_num_counter = 1000
    used_nums = set()
    item_id = 0

    for category in VALID_CATEGORIES:
        if category not in cat_files:
            continue
        files = cat_files[category]
        print(f"  [{category}] {len(files)} images...")

        for img_path in files:
            item_id += 1
            # deterministic unique number
            while item_num_counter in used_nums:
                item_num_counter += 1
            used_nums.add(item_num_counter)
            num = item_num_counter
            item_num_counter += 7

            # Copy image to images/ folder
            img_filename = f"item_{item_id:04d}.jpg"
            img_dst = IMAGES_DIR / category / img_filename
            shutil.copy2(img_path, img_dst)

            # Relative path for the catalog
            rel_path = f"images/{category}/{img_filename}"

            all_items.append({
                "id": f"item_{item_id:04d}",
                "itemNum": num,
                "description": img_path.stem.replace("_", " ").replace("-", " ").title(),
                "price": "",
                "category": category,
                "style": "",
                "image": rel_path,
            })
            print(f"    [{item_id}/{total}] {img_path.name} → No. {num} ({category})")

    print(f"\n  All {total} images copied. Writing catalog-data.js...")

    data = {
        "header": {
            "title": "Sew House",
            "phone": "213-308-0288",
            "email": "bridie@sewhousela.com",
            "logo": "SewHouseLA_Logo.png",
        },
        "itemsPerPage": 12,
        "showPrices": False,
        "items": all_items,
    }

    js_content = f"const CATALOG_DATA = {json.dumps(data, indent=2)};\n"
    with open(CATALOG_FILE, "w") as f:
        f.write(js_content)

    size_kb = CATALOG_FILE.stat().st_size / 1024
    print(f"\n✅ Built catalog-data.js")
    print(f"   Items: {total}")
    print(f"   Pottery:  {len([i for i in all_items if i['category'] == 'Pottery'])}")
    print(f"   Lighting: {len([i for i in all_items if i['category'] == 'Lighting'])}")
    print(f"   Statues:  {len([i for i in all_items if i['category'] == 'Statues'])}")
    print(f"   catalog-data.js: {size_kb:.1f} KB")
    print(f"   images/ folder: {IMAGES_DIR}")
    print(f"\nDeploy: upload the ENTIRE folder contents:")
    print(f"        catalog-data.js + catalog.html + SewHouseLA_Logo.png + images/")
    print(f"        to sewhousela.com/catalog/")


# ===== RESET =====

def run_reset():
    """Clear all progress and audited folders."""
    print("This will delete:")
    print(f"  - {PROGRESS_FILE}")
    print(f"  - All images in {AUDITED_DIR}/")
    print(f"  - {CATALOG_FILE}")
    confirm = input("Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Cancelled.")
        return

    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
    if CATALOG_FILE.exists():
        CATALOG_FILE.unlink()
    for subdir in AUDITED_DIR.iterdir():
        if subdir.is_dir():
            for f in subdir.iterdir():
                if f.is_file():
                    f.unlink()
    print("Reset complete. Raw images preserved in raw/")


# ===== MAIN =====

def main():
    parser = argparse.ArgumentParser(description="Sew House LA — Image categorization pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--auto", action="store_true", help="AI auto-categorization via Ollama")
    group.add_argument("--manual", action="store_true", help="Process images for manual audit")
    group.add_argument("--build", action="store_true", help="Build catalog-data.js from audited/")
    group.add_argument("--reset", action="store_true", help="Clear all progress and output")
    parser.add_argument("--model", default="moondream", help="Ollama vision model (default: moondream)")
    parser.add_argument("--host", default=OLLAMA_HOST, help="Ollama host")
    parser.add_argument("--batch", type=int, default=20, help="Pause after N images")
    parser.add_argument("--timeout", type=int, default=120, help="AI timeout per image")
    args = parser.parse_args()

    # Ensure directories exist
    RAW_DIR.mkdir(exist_ok=True)
    for cat in list(VALID_CATEGORIES) + ["Skipped", "Uncertain"]:
        (AUDITED_DIR / cat).mkdir(parents=True, exist_ok=True)

    if args.auto:
        run_auto(model=args.model, host=args.host, batch_size=args.batch, timeout=args.timeout)
    elif args.manual:
        run_manual()
    elif args.build:
        run_build()
    elif args.reset:
        run_reset()


if __name__ == "__main__":
    main()
