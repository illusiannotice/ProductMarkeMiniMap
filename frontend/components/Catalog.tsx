"use client";

import { useCallback, useEffect, useState } from "react";

import { ProductForm } from "@/components/ProductForm";
import { ApiError, type Me, type Product, fetchMe, fetchProducts } from "@/lib/api";
import { getAuthorization, initTelegram } from "@/lib/telegram";

type State =
  | { kind: "loading" }
  | { kind: "unauthenticated" }
  | { kind: "expired" }
  | { kind: "error" }
  | { kind: "ready"; authorization: string; me: Me; products: Product[]; nextOffset: number | null };

export function Catalog() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async () => {
    const authorization = getAuthorization();
    if (!authorization) {
      setState({ kind: "unauthenticated" });
      return;
    }
    try {
      const [me, page] = await Promise.all([fetchMe(authorization), fetchProducts(authorization)]);
      setState({ kind: "ready", authorization, me, products: page.items, nextOffset: page.next_offset });
    } catch (error) {
      setState({ kind: error instanceof ApiError && error.status === 401 ? "expired" : "error" });
    }
  }, []);

  useEffect(() => {
    initTelegram();
    void load();
  }, [load]);

  async function loadMore() {
    if (state.kind !== "ready" || state.nextOffset === null) return;
    setLoadingMore(true);
    try {
      const page = await fetchProducts(state.authorization, state.nextOffset);
      setState({ ...state, products: [...state.products, ...page.items], nextOffset: page.next_offset });
    } catch {
      setState({ kind: "error" });
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <main>
      <h1>Каталог</h1>
      {state.kind === "loading" && <p role="status">Загрузка…</p>}
      {state.kind === "unauthenticated" && <p>Откройте каталог через Telegram-бота, чтобы увидеть товары.</p>}
      {state.kind === "expired" && <p>Сессия Telegram устарела. Закройте и снова откройте Mini App.</p>}
      {state.kind === "error" && (
        <div role="alert">
          <p>Не удалось загрузить каталог.</p>
          <button type="button" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      )}
      {state.kind === "ready" && (
        <>
          {state.me.role === "Admin" && <ProductForm authorization={state.authorization} onCreated={() => void load()} />}
          {state.products.length === 0 ? (
            <p>Товаров пока нет.</p>
          ) : (
            <ul className="products">
              {state.products.map((product) => (
                <li key={product.id}>
                  <img src={product.image_url} alt={product.name} loading="lazy" />
                  <span>{product.name}</span>
                </li>
              ))}
            </ul>
          )}
          {state.nextOffset !== null && (
            <button type="button" onClick={() => void loadMore()} disabled={loadingMore}>
              {loadingMore ? "Загрузка…" : "Показать ещё"}
            </button>
          )}
        </>
      )}
    </main>
  );
}
