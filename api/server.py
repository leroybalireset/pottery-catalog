#!/usr/bin/env python3
"""
Sew House LA — Pottery Catalog API
Runs on VPS at /opt/pottery-api/server.py
Port 5001 (proxied via nginx at /api/)
"""

import base64
import json
import os
import shutil
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request
from PIL import Image as PILImage

app = Flask(__name__)

# ===== CONFIG =====
WWW_ROOT = Path("/var/www/pots.sewhousela.com")
IMAGES_DIR = WWW_ROOT / "images"
CATALOG_FILE = WWW_ROOT / "catalog-data.js"
UPLOAD_TMP = Path("/tmp/pottery-uploads")
OLLAMA_HOST = "http://localhost:11434"
CROP_SIZE = 800
JPEG_QUALITY = 92
VALID_CATEGORIES = {"Pottery", "Lighting", "Statues"}

AI_PROMPT = """Look at this image carefully. Categorize the item into exactly one of these three categories:
- Pottery (vases, pots, bowls, urns, ceramic vessels, planters)
- Lighting (lamps, sconces, pendants, chandeliers, light fixtures, candle holders)
- Statues (sculptures, figurines, totems, abstract forms, decorative figures)

Respond with ONLY the category name, nothing else. If truly uncertain, respond with "Uncertain"."""

UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
for cat in VALID_CATEGORIES:
    (IMAGES_DIR / cat).mkdir(parents=True, exist_ok=True)


# ===== HELPERS =====

def load_catalog() -> dict:
    if not CATALOG_FILE.exists():
        return {
            "header": {
                "title": "Sew House",
                "phone": "213-308-0288",
                "email": "bridie@sewhousela.com",
                "logo": "SewHouseLA_Logo.png",
            },
            "itemsPerPage": 12,
            "showPrices": False,
            "items": [],
        }
    content = CATALOG_FILE.read_text()
    # Strip "const CATALOG_DATA = " and trailing ";"
    content = content.strip()
    if content.startswith("const CATALOG_DATA ="):
        content = content[len("const CATALOG_DATA ="):].strip()
    if content.endswith(";"):
        content = content[:-1]
    return json.loads(content)


def save_catalog(data: dict):
    js = f"const CATALOG_DATA = {json.dumps(data, indent=2)};\n"
    CATALOG_FILE.write_text(js)


def next_item_id(items: list) -> tuple[str, int]:
    existing_ids = {i["id"] for i in items}
    existing_nums = {i["itemNum"] for i in items}
    n = 1
    while f"item_{n:04d}" in existing_ids:
        n += 1
    item_id = f"item_{n:04d}"
    num = 1000
    while num in existing_nums:
        num += 7
    return item_id, num


def process_image(src: Path, dst: Path) -> bool:
    try:
        img = PILImage.open(src).convert("RGB")
        w, h = img.size
        size = min(w, h)
        left = (w - size) // 2
        top = (h - size) // 2
        img = img.crop((left, top, left + size, top + size))
        img = img.resize((CROP_SIZE, CROP_SIZE), PILImage.LANCZOS)
        img.save(dst, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return True
    except Exception as e:
        app.logger.error(f"process_image failed: {e}")
        return False


def ai_categorize(image_path: Path) -> str:
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": "moondream", "prompt": AI_PROMPT, "images": [b64], "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        for cat in VALID_CATEGORIES:
            if cat.lower() in raw.lower():
                return cat
        return "Uncertain"
    except Exception as e:
        app.logger.error(f"ai_categorize failed: {e}")
        return "Uncertain"


# ===== ROUTES =====

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/catalog")
def get_catalog():
    return jsonify(load_catalog())


@app.route("/api/upload", methods=["POST"])
def upload():
    if "image" not in request.files:
        return jsonify({"error": "No image file"}), 400

    file = request.files["image"]
    category = request.form.get("category", "auto")
    description = request.form.get("description", "")

    # Save temp file
    tmp_path = UPLOAD_TMP / f"upload_{int(time.time())}.jpg"
    file.save(tmp_path)

    # AI categorize if not manually set
    if category == "auto" or category not in VALID_CATEGORIES:
        category = ai_categorize(tmp_path)
        if category not in VALID_CATEGORIES:
            category = "Pottery"  # fallback

    # Load current catalog
    data = load_catalog()
    item_id, item_num = next_item_id(data["items"])

    # Process and save image
    img_filename = f"{item_id}.jpg"
    img_dst = IMAGES_DIR / category / img_filename
    if not process_image(tmp_path, img_dst):
        tmp_path.unlink(missing_ok=True)
        return jsonify({"error": "Image processing failed"}), 500

    tmp_path.unlink(missing_ok=True)

    # Add to catalog
    rel_path = f"images/{category}/{img_filename}"
    item = {
        "id": item_id,
        "itemNum": item_num,
        "description": description or f"Item {item_num}",
        "price": "",
        "category": category,
        "style": "",
        "image": rel_path,
    }
    data["items"].append(item)
    save_catalog(data)

    # Fix permissions
    os.system(f"sudo chown -R www-data:www-data {WWW_ROOT}")

    return jsonify({"success": True, "item": item, "category": category})


@app.route("/api/item/<item_id>", methods=["PATCH"])
def update_item(item_id):
    data = load_catalog()
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if not item:
        return jsonify({"error": "Not found"}), 404

    body = request.get_json()
    for field in ("description", "price", "category", "style"):
        if field in body:
            item[field] = body[field]

    save_catalog(data)
    os.system(f"sudo chown -R www-data:www-data {WWW_ROOT}")
    return jsonify({"success": True, "item": item})


@app.route("/api/item/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    data = load_catalog()
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if not item:
        return jsonify({"error": "Not found"}), 404

    # Delete image file
    img_path = WWW_ROOT / item["image"]
    img_path.unlink(missing_ok=True)

    data["items"] = [i for i in data["items"] if i["id"] != item_id]
    save_catalog(data)
    os.system(f"sudo chown -R www-data:www-data {WWW_ROOT}")
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
