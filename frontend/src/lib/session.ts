import "server-only";
import { createHmac, timingSafeEqual } from "crypto";
import { cookies } from "next/headers";

const COOKIE_NAME = "session";
const SESSION_DURATION_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function secret(): string {
  const s = process.env.SESSION_SECRET;
  if (!s) throw new Error("SESSION_SECRET is not set");
  return s;
}

function sign(value: string): string {
  return createHmac("sha256", secret()).update(value).digest("base64url");
}

// expiresAt|hmac(expiresAt) — no user identity to carry, just "was the
// correct SITE_PASSWORD entered before this timestamp".
export function createSessionToken(): string {
  const expiresAt = String(Date.now() + SESSION_DURATION_MS);
  return `${expiresAt}.${sign(expiresAt)}`;
}

export function verifySessionToken(token: string | undefined): boolean {
  if (!token) return false;
  const [expiresAt, signature] = token.split(".");
  if (!expiresAt || !signature) return false;

  const expected = sign(expiresAt);
  const a = Buffer.from(signature);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return false;

  return Date.now() < Number(expiresAt);
}

export async function createSession() {
  const store = await cookies();
  store.set(COOKIE_NAME, createSessionToken(), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_DURATION_MS / 1000,
  });
}

export async function deleteSession() {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

export { COOKIE_NAME };
