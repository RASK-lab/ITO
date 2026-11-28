import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  BACKEND: DurableObjectNamespace<Backend>;
  ASSETS: Fetcher;
}

export class Backend extends Container {
  defaultPort = 8000;
  sleepAfter = "2m";
}

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