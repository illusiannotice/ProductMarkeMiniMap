"use client";

import { type FormEvent, useState } from "react";

import { ApiError, createProduct } from "@/lib/api";

const MAX_NAME_LENGTH = 120;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp";

const STATUS_MESSAGES: Record<number, string> = {
  401: "Сессия Telegram устарела. Откройте Mini App заново.",
  403: "Добавлять товары может только администратор.",
  413: "Файл слишком большой. Максимальный размер — 5 МБ.",
  415: "Поддерживаются только изображения JPEG, PNG и WebP.",
  422: "Проверьте название и фото.",
};

interface Props {
  authorization: string;
  onCreated: () => void;
}

export function ProductForm({ authorization, onCreated }: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const nameInput = form.elements.namedItem("name") as HTMLInputElement;
    const imageInput = form.elements.namedItem("image") as HTMLInputElement;
    const name = nameInput.value.trim();
    const image = imageInput.files?.[0];

    setError(null);
    setSuccess(null);
    if (!name) {
      setError("Укажите название товара.");
      return;
    }
    if (!image || image.size === 0) {
      setError("Выберите фото товара.");
      return;
    }
    if (image.size > MAX_IMAGE_BYTES) {
      setError(STATUS_MESSAGES[413]);
      return;
    }

    setSubmitting(true);
    try {
      const product = await createProduct(authorization, name, image);
      form.reset();
      setSuccess(`Товар «${product.name}» добавлен.`);
      onCreated();
    } catch (caught) {
      const status = caught instanceof ApiError ? caught.status : 0;
      setError(STATUS_MESSAGES[status] ?? "Не удалось сохранить товар. Попробуйте ещё раз.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Новый товар">
      <h2>Новый товар</h2>
      <label>
        Название
        <input name="name" type="text" maxLength={MAX_NAME_LENGTH} required />
      </label>
      <label>
        Фото
        <input name="image" type="file" accept={ACCEPTED_TYPES} required />
      </label>
      <button type="submit" disabled={submitting}>
        {submitting ? "Сохранение…" : "Добавить товар"}
      </button>
      {error && <p role="alert">{error}</p>}
      {success && <p role="status">{success}</p>}
    </form>
  );
}
