interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

function webApp(): TelegramWebApp | undefined {
  return typeof window === "undefined" ? undefined : window.Telegram?.WebApp;
}

export function initTelegram(): void {
  const app = webApp();
  if (!app?.initData) return;
  app.ready();
  app.expand();
}

export function getAuthorization(): string | null {
  const initData = webApp()?.initData;
  if (initData) return `tma ${initData}`;

  const devTelegramId = process.env.NEXT_PUBLIC_DEV_AUTH_TELEGRAM_ID;
  if (process.env.NODE_ENV === "development" && devTelegramId && /^\d+$/.test(devTelegramId)) {
    return `dev ${devTelegramId}`;
  }
  return null;
}
