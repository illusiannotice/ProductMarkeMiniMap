import { describe, expect, it } from "vitest";

import { ApiError, createProduct, fetchMe, fetchProducts } from "@/lib/api";
import { authorizationOf, jsonResponse, stubFetch } from "./helpers";

describe("api client", () => {
  it("forwards the Telegram authorization header", async () => {
    const fetchMock = stubFetch(() => jsonResponse({ telegram_id: 1, role: "User" }));
    await fetchMe("tma init-data");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/auth/me");
    expect(authorizationOf(init)).toBe("tma init-data");
    expect(init?.cache).toBe("no-store");
  });

  it("requests products with numeric pagination", async () => {
    const fetchMock = stubFetch(() => jsonResponse({ items: [], next_offset: null }));
    await fetchProducts("tma x", 50);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/products?limit=50&offset=50");
  });

  it("sends new products as multipart form data", async () => {
    const fetchMock = stubFetch(() => jsonResponse({ id: "1", name: "Lamp" }, 201));
    const image = new File(["png"], "lamp.png", { type: "image/png" });
    await createProduct("tma x", "Lamp", image);

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    const body = init?.body as FormData;
    expect(body.get("name")).toBe("Lamp");
    expect((body.get("image") as File).name).toBe("lamp.png");
    expect(authorizationOf(init)).toBe("tma x");
  });

  it("raises ApiError with the response status and detail", async () => {
    stubFetch(() => jsonResponse({ detail: "Administrator role required" }, 403));
    const error = await fetchMe("tma x").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, message: "Administrator role required" });
  });
});
