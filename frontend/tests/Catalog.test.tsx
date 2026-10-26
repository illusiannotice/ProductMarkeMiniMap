import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Catalog } from "@/components/Catalog";
import type { Product } from "@/lib/api";
import { authorizationOf, jsonResponse, stubFetch, stubTelegram } from "./helpers";

const lamp: Product = {
  id: "p1",
  name: "Lamp",
  image_url: "https://cdn.test/lamp.png",
  created_at: "2026-10-23T00:00:00Z",
};

function me(role: "User" | "Admin") {
  return { telegram_id: 1, username: "ann", first_name: "Ann", last_name: null, role };
}

// jsdom's constraint validation does not see files set by user-event, so submit the form directly.
async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, form: HTMLElement) {
  await user.type(screen.getByLabelText("Название"), "Chair");
  await user.upload(screen.getByLabelText("Фото"), new File(["png"], "chair.png", { type: "image/png" }));
  fireEvent.submit(form);
}

function stubApi(role: "User" | "Admin", products: Product[] = [lamp]) {
  return stubFetch((url, init) => {
    if (url === "/api/v1/auth/me") return jsonResponse(me(role));
    if (url.startsWith("/api/v1/products") && init.method === "POST") {
      return jsonResponse({ ...lamp, id: "p2", name: "Chair" }, 201);
    }
    if (url.startsWith("/api/v1/products")) return jsonResponse({ items: products, next_offset: null });
    return jsonResponse({ detail: "Not Found" }, 404);
  });
}

describe("Catalog", () => {
  it("asks to open the catalog through Telegram in a normal browser", async () => {
    const fetchMock = stubFetch(() => jsonResponse({}));
    render(<Catalog />);
    expect(screen.getByRole("heading", { name: "Каталог" })).toBeInTheDocument();
    expect(await screen.findByText(/через Telegram-бота/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows products to a user without the admin form", async () => {
    stubTelegram();
    const fetchMock = stubApi("User");
    render(<Catalog />);

    expect(await screen.findByText("Lamp")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Lamp" })).toHaveAttribute("src", lamp.image_url);
    expect(screen.queryByRole("form", { name: "Новый товар" })).not.toBeInTheDocument();
    for (const [, init] of fetchMock.mock.calls) {
      expect(authorizationOf(init)).toMatch(/^tma /);
    }
  });

  it("shows the empty state", async () => {
    stubTelegram();
    stubApi("User", []);
    render(<Catalog />);
    expect(await screen.findByText("Товаров пока нет.")).toBeInTheDocument();
  });

  it("explains expired Telegram sessions", async () => {
    stubTelegram();
    stubFetch(() => jsonResponse({ detail: "Invalid or missing Telegram authentication" }, 401));
    render(<Catalog />);
    expect(await screen.findByText(/Сессия Telegram устарела/)).toBeInTheDocument();
  });

  it("shows a retryable error when the API fails", async () => {
    stubTelegram();
    stubFetch(() => jsonResponse({ detail: "Internal server error" }, 500));
    render(<Catalog />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось загрузить каталог.");
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });

  it("lets an admin add a product and refreshes the list", async () => {
    stubTelegram();
    const fetchMock = stubApi("Admin");
    const user = userEvent.setup();
    render(<Catalog />);

    const form = await screen.findByRole("form", { name: "Новый товар" });
    await fillAndSubmit(user, form);

    expect(await screen.findByRole("status")).toHaveTextContent("Товар «Chair» добавлен.");
    expect(form).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post).toBeDefined();
    expect(authorizationOf(post?.[1])).toMatch(/^tma /);
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([url]) => url === "/api/v1/auth/me")).toHaveLength(2),
    );
  });

  it("shows a role error if the API refuses the upload", async () => {
    stubTelegram();
    stubFetch((url, init) => {
      if (url === "/api/v1/auth/me") return jsonResponse(me("Admin"));
      if (init.method === "POST") return jsonResponse({ detail: "Administrator role required" }, 403);
      return jsonResponse({ items: [], next_offset: null });
    });
    const user = userEvent.setup();
    render(<Catalog />);

    await fillAndSubmit(user, await screen.findByRole("form", { name: "Новый товар" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("только администратор");
  });
});
