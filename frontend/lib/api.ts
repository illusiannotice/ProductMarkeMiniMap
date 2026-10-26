export type Role = "User" | "Admin";

export interface Me {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  role: Role;
}

export interface Product {
  id: string;
  name: string;
  image_url: string;
  created_at: string;
}

export interface ProductPage {
  items: Product[];
  next_offset: number | null;
}

export const PAGE_SIZE = 50;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, authorization: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", authorization);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : response.statusText);
  }
  return (await response.json()) as T;
}

export function fetchMe(authorization: string): Promise<Me> {
  return request<Me>("/api/v1/auth/me", authorization);
}

export function fetchProducts(authorization: string, offset = 0): Promise<ProductPage> {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  return request<ProductPage>(`/api/v1/products?${query}`, authorization);
}

export function createProduct(authorization: string, name: string, image: File): Promise<Product> {
  const form = new FormData();
  form.append("name", name);
  form.append("image", image);
  return request<Product>("/api/v1/products", authorization, { method: "POST", body: form });
}
