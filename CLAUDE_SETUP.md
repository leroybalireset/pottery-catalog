# Claude Setup Guide: pots.sewhousela.com

> For Claude (or any assistant) running on the VPS at `89.167.88.232`

## Goal
Set up `pots.sewhousela.com` as a static-file subdomain serving the Sew House LA pottery catalog.

## Prerequisites
- VPS IP: `89.167.88.232`
- User: `aaron` (has passwordless sudo)
- Web server: `nginx` (already running for sewhousela.com)
- SSL: `certbot` (already installed for sewhousela.com)

---

## Step 1: Add DNS A Record

The user needs to add a DNS A record for `pots.sewhousela.com` pointing to `89.167.88.232`.

**If DNS is already configured** (verify with `dig pots.sewhousela.com`), skip this step.

**If DNS is NOT configured yet**, tell the user:
> "Please add an A record for `pots.sewhousela.com` pointing to `89.167.88.232` in your DNS provider (Cloudflare, Namecheap, etc.). Then run this script again."

---

## Step 2: Create Directory

```bash
sudo mkdir -p /var/www/pots.sewhousela.com
sudo chown -R www-data:www-data /var/www/pots.sewhousela.com
sudo chmod -R 755 /var/www/pots.sewhousela.com
```

---

## Step 3: Create Nginx Config

Create `/etc/nginx/sites-available/pots.sewhousela.com`:

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

Enable it:

```bash
sudo ln -sf /etc/nginx/sites-available/pots.sewhousela.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 4: Get SSL Certificate

```bash
sudo certbot --nginx -d pots.sewhousela.com --non-interactive --agree-tos --email bridie@sewhousela.com
```

If certbot fails because DNS isn't propagated yet, wait a few minutes and retry.

Verify auto-renewal:
```bash
sudo certbot renew --dry-run
```

---

## Step 5: Verify Setup

```bash
curl -s -o /dev/null -w "%{http_code}" http://pots.sewhousela.com/
# Should return 200 (or 301 if certbot added redirect)

curl -s -o /dev/null -w "%{http_code}" https://pots.sewhousela.com/
# Should return 200
```

---

## Step 6: Notify User

Tell the user:
> "Server setup complete! `pots.sewhousela.com` is ready. Now run `./deploy.sh` from the Mac to push the catalog files."

---

## Troubleshooting

### DNS not resolving
```bash
dig +short pots.sewhousela.com
# Should return 89.167.88.232
```
If empty, DNS record hasn't propagated. Wait 1-60 minutes depending on TTL.

### Certbot fails
```bash
sudo certbot certonly --nginx -d pots.sewhousela.com --dry-run
```
Check error output. Common causes: DNS not propagated, rate limit hit, nginx config syntax error.

### 403 Forbidden
```bash
sudo chown -R www-data:www-data /var/www/pots.sewhousela.com
sudo chmod -R 755 /var/www/pots.sewhousela.com
```

### Nginx test fails
```bash
sudo nginx -t
# Fix any syntax errors before reloading
```

---

## File Structure After Deploy

```
/var/www/pots.sewhousela.com/
├── catalog.html          ← Main catalog page
├── catalog-data.js       ← Item data (JSON)
├── SewHouseLA_Logo.png   ← Logo image
└── images/
    ├── Pottery/
    │   ├── item_0001.jpg
    │   └── ...
    ├── Lighting/
    │   ├── item_0011.jpg
    │   └── ...
    └── Statues/
        ├── item_0021.jpg
        └── ...
```

---

## One-Liner Setup Script (optional)

If the user wants, you can run everything at once:

```bash
#!/bin/bash
set -e
DOMAIN="pots.sewhousela.com"
ROOT="/var/www/$DOMAIN"

echo "[1/5] Creating directory..."
sudo mkdir -p "$ROOT"
sudo chown -R www-data:www-data "$ROOT"
sudo chmod -R 755 "$ROOT"

echo "[2/5] Writing nginx config..."
cat << 'EOF' | sudo tee /etc/nginx/sites-available/$DOMAIN
server {
    listen 80;
    listen [::]:80;
    server_name pots.sewhousela.com;
    root /var/www/pots.sewhousela.com;
    index catalog.html;
    location ~ /\.(?!well-known) { deny all; }
    location / { try_files $uri $uri/ =404; }
    location ~* \.(jpg|jpeg|png|gif|webp|svg)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

echo "[3/5] Enabling site..."
sudo ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

echo "[4/5] Getting SSL certificate..."
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email bridie@sewhousela.com || true

echo "[5/5] Done!"
echo "Visit: https://$DOMAIN"
```
