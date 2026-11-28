cd front
npm ci
npm run build

cd ../infra/cloudflare
npm ci
npx wrangler dev