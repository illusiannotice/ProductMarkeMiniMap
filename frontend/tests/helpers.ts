import { vi } from "vitest";

export const INIT_DATA = "query_id=AA&user=%7B%22id%22%3A1%7D&auth_date=1&hash=abc";

export function stubTelegram(initData = INIT_DATA) {
  const app = { initData, ready: vi.fn(), expand: vi.fn() };
  window.Telegram = { WebApp: app };
  return app;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Route = (url: string, init: RequestInit) => Response | Promise<Response>;

export function stubFetch(route: Route) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init: RequestInit = {}) =>
    Promise.resolve(route(String(input), init)),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function authorizationOf(init: RequestInit | undefined): string | null {
  return new Headers(init?.headers).get("Authorization");
}
