import { Container, getContainer } from "@cloudflare/containers";

// (A) コンテナからの外向き通信を Worker で受けるために必要
export { ContainerProxy } from "@cloudflare/containers";

interface Env {
  BACKEND: DurableObjectNamespace<Backend>;
  ASSETS: Fetcher;
  DRAWINGS: R2Bucket; // (B) wrangler.jsonc の r2_buckets
  DB: D1Database; // (B) wrangler.jsonc の d1_databases
}

// バックエンドが保存を頼む先。実在しない名前で、Worker の中で受け取る（公開されない）
const STORE_HOST = "ito.store";

// back/src/storage.py の _KEY_PATTERN と同じ
const KEY_PATTERN = /^[a-z0-9_-]+(\/[a-z0-9_.-]+)+$/;

// /db/query で通す SQL（念のため必要なものだけ）
const ALLOWED_SQL = [/^\s*INSERT\s+INTO\s+drawings\b/i, /^\s*SELECT\b/i];

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

// (C) バックエンドからの依頼を受ける口
async function handleStore(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname.startsWith("/objects/")) {
    const key = decodeURIComponent(url.pathname.slice("/objects/".length));
    if (!KEY_PATTERN.test(key) || key.includes("..")) {
      return json({ error: "invalid key" }, 400);
    }

    switch (request.method) {
      case "PUT":
        await env.DRAWINGS.put(key, await request.arrayBuffer());
        return new Response(null, { status: 204 });
      case "DELETE":
        await env.DRAWINGS.delete(key);
        return new Response(null, { status: 204 });
      case "GET": {
        const object = await env.DRAWINGS.get(key);
        if (!object) return json({ error: "not found" }, 404);
        const headers = new Headers();
        object.writeHttpMetadata(headers);
        headers.set("etag", object.httpEtag);
        return new Response(object.body, { headers });
      }
      default:
        return json({ error: "method not allowed" }, 405);
    }
  }

  if (url.pathname === "/db/query" && request.method === "POST") {
    let sql: unknown;
    let params: unknown;
    try {
      ({ sql, params = [] } = (await request.json()) as { sql?: unknown; params?: unknown });
    } catch {
      return json({ error: "invalid json" }, 400);
    }
    if (typeof sql !== "string" || !Array.isArray(params)) {
      return json({ error: "sql must be a string and params an array" }, 400);
    }
    if (!ALLOWED_SQL.some((pattern) => pattern.test(sql))) {
      return json({ error: "sql not allowed" }, 403);
    }
    try {
      const { results } = await env.DB.prepare(sql).bind(...params).all();
      return json({ results });
    } catch (error) {
      return json({ error: String(error) }, 500);
    }
  }

  return json({ error: "not found" }, 404);
}

export class Backend extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = "5m";

  // (D) コンテナに渡す環境変数。これがあるとバックエンドは Worker 経由で保存する
  envVars = {
    ITO_STORE_URL: `http://${STORE_HOST}`,
  };
}

// (E) クラスの中に static で書くと登録されないので、必ず外で代入する
Backend.outboundByHost = {
  [STORE_HOST]: (request: Request, env: unknown) => handleStore(request, env as Env),
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/")) {
      const container = getContainer(env.BACKEND, "backend");
      return container.fetch(request);
    }

    return env.ASSETS.fetch(request);
  },
};