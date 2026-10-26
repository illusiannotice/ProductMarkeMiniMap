import { describe, expect, it, vi } from "vitest";

import { getAuthorization, initTelegram } from "@/lib/telegram";
import { INIT_DATA, stubTelegram } from "./helpers";

describe("telegram auth", () => {
  it("uses Telegram init data when running inside Telegram", () => {
    const app = stubTelegram();
    initTelegram();
    expect(getAuthorization()).toBe(`tma ${INIT_DATA}`);
    expect(app.ready).toHaveBeenCalled();
    expect(app.expand).toHaveBeenCalled();
  });

  it("returns null in a normal browser", () => {
    expect(getAuthorization()).toBeNull();
  });

  it("returns null when the Telegram script loads outside Telegram", () => {
    stubTelegram("");
    expect(getAuthorization()).toBeNull();
  });

  it("never uses the dev identity outside development builds", () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_TELEGRAM_ID", "42");
    vi.stubEnv("NODE_ENV", "production");
    expect(getAuthorization()).toBeNull();
  });

  it("uses the dev identity only in development builds", () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_TELEGRAM_ID", "42");
    vi.stubEnv("NODE_ENV", "development");
    expect(getAuthorization()).toBe("dev 42");
  });
});
