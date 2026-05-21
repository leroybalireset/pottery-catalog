#!/bin/bash
# Sew House LA — Catalog Deploy Script
# Pushes catalog files from local Mac to VPS at pots.sewhousela.com
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Prerequisites:
#   - SSH key auth to VPS is configured (~/.ssh/config has Host 89.167.88.232)
#   - Claude has run the server setup on the VPS first (see CLAUDE_SETUP.md)

set -e

VPS_USER="aaron"
VPS_HOST="89.167.88.232"
REMOTE_DIR="/var/www/pots.sewhousela.com"
LOCAL_DIR="/Users/aaronowens/pottery_catalog"

echo "========================================"
echo " Sew House LA Catalog Deploy"
echo "========================================"
echo ""

# Check local files exist
echo "Checking local files..."
if [ ! -f "$LOCAL_DIR/catalog.html" ]; then
    echo "ERROR: catalog.html not found in $LOCAL_DIR"
    echo "Run: cd $LOCAL_DIR && python3 categorize.py --build"
    exit 1
fi

if [ ! -f "$LOCAL_DIR/catalog-data.js" ]; then
    echo "ERROR: catalog-data.js not found in $LOCAL_DIR"
    echo "Run: cd $LOCAL_DIR && python3 categorize.py --build"
    exit 1
fi

if [ ! -d "$LOCAL_DIR/images" ]; then
    echo "ERROR: images/ folder not found in $LOCAL_DIR"
    echo "Run: cd $LOCAL_DIR && python3 categorize.py --build"
    exit 1
fi

if [ ! -f "$LOCAL_DIR/SewHouseLA_Logo.png" ]; then
    echo "ERROR: SewHouseLA_Logo.png not found in $LOCAL_DIR"
    exit 1
fi

# Check SSH connectivity
echo "Checking VPS connectivity..."
if ! ssh -o ConnectTimeout=5 "$VPS_USER@$VPS_HOST" "echo 'VPS reachable'" > /dev/null 2>&1; then
    echo "ERROR: Cannot SSH to $VPS_USER@$VPS_HOST"
    echo "Make sure SSH key auth is configured in ~/.ssh/config"
    exit 1
fi

# Check remote directory exists (Claude should have created it)
echo "Checking remote directory..."
if ! ssh "$VPS_USER@$VPS_HOST" "[ -d $REMOTE_DIR ]" 2>/dev/null; then
    echo "ERROR: Remote directory $REMOTE_DIR does not exist."
    echo "Have Claude run the setup from CLAUDE_SETUP.md first."
    exit 1
fi

# Rsync the files (temporarily give aaron ownership so rsync can write)
echo ""
echo "Deploying files to $VPS_HOST:$REMOTE_DIR ..."
ssh "$VPS_USER@$VPS_HOST" "sudo chown -R $VPS_USER:$VPS_USER $REMOTE_DIR"

rsync -avz --delete \
    "$LOCAL_DIR/catalog.html" \
    "$LOCAL_DIR/catalog-data.js" \
    "$LOCAL_DIR/SewHouseLA_Logo.png" \
    "$LOCAL_DIR/images/" \
    "$VPS_USER@$VPS_HOST:$REMOTE_DIR/"

# Restore nginx ownership
echo ""
echo "Setting file permissions..."
ssh "$VPS_USER@$VPS_HOST" "sudo chown -R www-data:www-data $REMOTE_DIR && sudo chmod -R 755 $REMOTE_DIR"

# Reload nginx
echo "Reloading nginx..."
ssh "$VPS_USER@$VPS_HOST" "sudo nginx -t && sudo systemctl reload nginx"

echo ""
echo "========================================"
echo " DEPLOY COMPLETE"
echo "========================================"
echo ""
echo "Visit: https://pots.sewhousela.com"
echo ""
