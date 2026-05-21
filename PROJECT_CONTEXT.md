# Sew House LA — Pottery Catalog Project

> Complete context for Claude or any developer picking up this project.

---

## What This Is

A **static, client-side product catalog** for Sew House LA (Bridie's pottery & home goods business). No backend, no database, no server required. Everything runs in the browser.

**Live URL:** `https://pots.sewhousela.com`

**Features:**
- Category sections: **Pottery**, **Lighting**, **Statues**
- Section pagination (12 items per page)
- Interest list ("My List") — clients click items, then print or email a pricing request
- Search by item number
- Responsive grid layout
- Auto-crop images to centered square on upload
- Duplicate image detection (perceptual hash)
- Auto-generated unique 4-digit item numbers

**Critical business rule:** Prices are NEVER shown to customers. Admin enters prices for internal tracking, but the catalog only shows item numbers and descriptions. Customers select items into "My List" and click "Request Pricing" to email `bridie@sewhousela.com`.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Pure HTML5 + CSS + vanilla JavaScript |
| Data format | `catalog-data.js` — a JS file that sets `window.CATALOG_DATA` |
| Images | JPEG, served as separate files in `images/{category}/` |
| Image processing | Pillow (Python) for crop/resize |
| AI categorization | Ollama with vision models (moondream/llava/llama3.2-vision) |
| Web server | Nginx (on VPS) |
| SSL | Let's Encrypt via certbot |

---

## File Inventory

### Public-facing files (deployed to server)

| File | Purpose | Size (typical) |
|------|---------|---------------|
| `catalog.html` | The public catalog website | ~45 KB |
| `catalog-data.js` | Item metadata + image paths | ~7 KB per 30 items |
| `SewHouseLA_Logo.png` | Header logo | ~4 KB |
| `images/Pottery/*.jpg` | Pottery photos | ~180 KB each |
| `images/Lighting/*.jpg` | Lighting photos | ~180 KB each |
| `images/Statues/*.jpg` | Statue photos | ~180 KB each |

### Admin/builder files (local only, not deployed)

| File | Purpose |
|------|---------|
| `admin.html` | Full admin: upload, edit, reorder, preview, export. Has duplicate detection, drag-and-drop reordering, price sheet preview. |
| `audit.html` | Rapid manual categorization with hotkeys. Drop images → press `1`/`2`/`3`/`S` → export. |
| `sample.html` | Demo preview with 58 placeholder items to test layout/pagination without real data. |
| `categorize.py` | Pipeline script: processes raw images, optionally AI-categorizes, builds `catalog-data.js`. |
| `deploy.sh` | One-command deploy from Mac to VPS via rsync + ssh. |
| `raw/` | Drop original photos here for processing. |
| `audited/{Pottery,Lighting,Statues,Skipped,Uncertain}/` | Processed & categorized images. |
| `images/` | **Output** — processed images copied here during `--build`, then deployed. |
| `categorized.json` | Progress tracking for AI categorization (auto-generated). |

---

## Architecture

### Data Flow

```
Raw photos (from camera/phone)
    ↓
[Drop in raw/]
    ↓
categorize.py --manual  →  crops to 800x800, saves in audited/Uncertain/
    ↓
[audit.html OR drag in Finder]
    ↓
Sort into audited/Pottery/, audited/Lighting/, audited/Statues/
    ↓
categorize.py --build   →  copies images to images/, writes catalog-data.js
    ↓
./deploy.sh             →  rsync to VPS at /var/www/pots.sewhousela.com/
    ↓
https://pots.sewhousela.com  (live catalog)
```

### Alternative: AI Categorization

```
Raw photos
    ↓
categorize.py --auto    →  processes + sends each image to local Ollama vision model
    ↓
AI suggests category (Pottery/Lighting/Statues)
    ↓
Review in audit.html, correct any mistakes
    ↓
categorize.py --build
    ↓
./deploy.sh
```

### `catalog-data.js` Structure

```javascript
const CATALOG_DATA = {
  header: {
    title: "Sew House",
    phone: "213-308-0288",
    email: "bridie@sewhousela.com",
    logo: "SewHouseLA_Logo.png"
  },
  itemsPerPage: 12,
  showPrices: false,
  items: [
    {
      id: "item_0001",
      itemNum: 1000,
      description: "Hand Thrown Stoneware Vase",
      price: "",           // always empty in catalog view
      category: "Pottery",
      style: "",
      image: "images/Pottery/item_0001.jpg"
    }
  ]
};
```

---

## Key Design Decisions

### 1. Images as separate files (not base64 embedded)
**Why:** For ~800 items, base64 would make `catalog-data.js` 150-200 MB. Browsers choke on inline scripts that large. Separate files load lazily, cache individually, and the JS file stays tiny (~7 KB).

**Trade-off:** Must deploy the entire `images/` folder alongside `catalog.html`.

### 2. Section pagination (not global pagination)
**Why:** Each category gets its own pagination bar. A customer browsing Pottery doesn't lose their place when they jump to Lighting. Critical for ~800 items where Pottery might have 400 items = 34 pages.

**Implementation:** `SECTION_SIZE = 12`. `sectionPages` object tracks current page per category.

### 3. No prices in catalog
**Why:** Business requirement. Prices are entered in `admin.html` for Bridie's internal use (price sheets, inventory tracking) but never shown to customers.

**Customer flow:** Browse → click "+" to add to My List → click "Request Pricing" → opens email to `bridie@sewhousela.com` with item numbers and descriptions.

### 4. Auto-crop to centered square
**Why:** Photos come from phones in all orientations. Center-crop ensures consistent grid cards without distortion. Crop size is 800×800px from the center of the image, then saved as JPEG quality 92.

### 5. Perceptual hash duplicate detection
**Why:** Prevents uploading the same photo twice (or nearly the same photo resized/recompressed). Uses aHash (8×8 grayscale average hash). Hamming distance ≤ 5 flags as duplicate.

**Threshold:** 5 bits different out of 64. Catches exact duplicates, resizes, recompressions. Intentionally allows different angles of the same pot.

### 6. Pure client-side (no backend)
**Why:** Simplicity. No server to maintain, no database, no API. Deploy is just `rsync` static files. Works on any web host (Netlify, Vercel, S3, nginx, etc.).

**Trade-off:** Images must be pre-processed and embedded/exported before deployment. No dynamic uploads from customers.

---

## How to Use Each Tool

### `audit.html` — Manual Categorization (Browser)

```bash
open audit.html
```

1. Drop images into the drop zone (or click to browse)
2. Images appear in a thumbnail grid
3. Click **"Audit Mode"** for fullscreen view
4. Press hotkeys for each image:
   - `1` → Pottery
   - `2` → Lighting
   - `3` → Statues
   - `S` → Skip (excludes from export)
   - `←` / `→` → navigate
   - `Esc` → exit audit mode
5. Click **"Export catalog-data.js"** when done

### `categorize.py` — Pipeline Script

```bash
# Process raw images (crop + resize), place in audited/Uncertain/
python3 categorize.py --manual

# AI auto-categorize (requires Ollama vision model)
python3 categorize.py --auto

# Build catalog-data.js from audited/ folders
python3 categorize.py --build

# Clear all progress (keeps raw/)
python3 categorize.py --reset
```

### `admin.html` — Full Admin (Browser)

```bash
open admin.html
```

Features: upload zone, drag-and-drop reordering, edit descriptions/prices/categories, duplicate detection dialog, live preview, price sheet preview, export `catalog-data.js`.

**Note:** `admin.html` exports with base64-embedded images (legacy format). For large catalogs, use `categorize.py --build` instead, which outputs image paths.

### `deploy.sh` — Deploy to VPS

```bash
./deploy.sh
```

Prerequisites:
- `pots.sewhousela.com` DNS A record points to `89.167.88.232`
- Claude has run server setup (`CLAUDE_SETUP.md`)
- SSH key auth configured (`~/.ssh/config` has Host `89.167.88.232`)

---

## Folder Structure (Local)

```
pottery_catalog/
├── raw/                          ← Drop original photos here
│
├── audited/                      ← Working categorized images
│   ├── Pottery/
│   ├── Lighting/
│   ├── Statues/
│   ├── Skipped/
│   └── Uncertain/
│
├── images/                       ← DEPLOY output (copied from audited/)
│   ├── Pottery/
│   ├── Lighting/
│   └── Statues/
│
├── catalog.html                  ← Public catalog (deploy)
├── catalog-data.js               ← Catalog data (deploy, rebuilt by --build)
├── SewHouseLA_Logo.png          ← Logo (deploy)
│
├── admin.html                    ← Full admin tool (local)
├── audit.html                    ← Manual categorization (local)
├── sample.html                   ← Demo preview (local)
├── categorize.py                 ← Pipeline script
├── deploy.sh                     ← Deploy script
│
├── CLAUDE_SETUP.md               ← VPS setup instructions for Claude
├── PROJECT_CONTEXT.md            ← This file
└── categorized.json              ← AI progress tracking (auto)
```

---

## Folder Structure (Server)

```
/var/www/pots.sewhousela.com/
├── catalog.html
├── catalog-data.js
├── SewHouseLA_Logo.png
└── images/
    ├── Pottery/
    ├── Lighting/
    └── Statues/
```

---

## Nginx Config (on VPS)

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name pots.sewhousela.com;

    root /var/www/pots.sewhousela.com;
    index catalog.html;

    location ~ /\.(?!well-known) { deny all; }

    location / {
        try_files $uri $uri/ =404;
    }

    # Cache images for 30 days
    location ~* \.(jpg|jpeg|png|gif|webp|svg)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
}
```

Certbot will add the SSL/HTTPS block automatically.

---

## Scaling to ~800 Items

| Concern | Current | At 800 items | Mitigation |
|---------|---------|-------------|------------|
| `catalog-data.js` size | ~7 KB (30 items) | ~180 KB | Negligible — text-only metadata |
| Images total size | ~5 MB (30 items) | ~140 MB | Fine for nginx + CDN caching |
| Initial page load | Fast | Fast | Images load lazily, paginated |
| Browser memory | Low | Medium | Only visible images load |
| Build time | ~5s | ~2 min | Acceptable, run once per batch |
| Deploy time | ~10s | ~3 min | rsync is efficient |

**If images get too large:**
- Compress further: `cwebp` or lower JPEG quality
- Use a CDN (Cloudflare, CloudFront) in front of nginx
- Lazy-load with IntersectionObserver (already partially implemented)

---

## Known Issues & Limitations

1. **AI categorization requires downloading a vision model** (~2-8 GB via Ollama). On slow connections this takes 10-20 minutes. Manual mode works immediately without it.

2. **No mobile app.** The catalog is responsive web, works on phones, but no native app.

3. **No user accounts.** "My List" is stored in `localStorage` per browser. If a customer clears cookies, their list disappears.

4. **Email "Request Pricing" uses `mailto:` link.** Requires the customer to have an email client configured. For a smoother experience, a simple Formspree or Netlify Form could be added later.

5. **admin.html exports base64 images.** For large catalogs, use `categorize.py --build` instead to get image-path-based output.

---

## Contact

- **Business:** Sew House LA
- **Phone:** 213-308-0288
- **Email:** bridie@sewhousela.com
- **VPS IP:** 89.167.88.232
- **User:** aaron (has passwordless sudo)

---

## Quick Reference

```bash
# Full workflow from raw photos to live site:
cd /Users/aaronowens/pottery_catalog
python3 categorize.py --manual          # process images
open audit.html                          # categorize with hotkeys
python3 categorize.py --build           # build catalog-data.js
./deploy.sh                              # deploy to VPS

# Or with AI:
ollama pull moondream                   # download vision model (one-time)
python3 categorize.py --auto            # AI categorizes
python3 categorize.py --build
./deploy.sh
```
