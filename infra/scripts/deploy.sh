#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== Build frontend ==="
cd "$ROOT_DIR/front"
npm ci
npm run build

echo "=== Install Cloudflare dependencies ==="
cd "$ROOT_DIR/infra/cloudflare"
npm ci

echo "=== Deploy to Cloudflare ==="
npx wrangler deploy

echo "=== Deployment completed ==="