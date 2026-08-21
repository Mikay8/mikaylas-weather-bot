"use server";

import { timingSafeEqual } from "crypto";
import { redirect } from "next/navigation";
import { createSession } from "@/lib/session";

function passwordMatches(candidate: string): boolean {
  const expected = process.env.SITE_PASSWORD;
  if (!expected) throw new Error("SITE_PASSWORD is not set");

  const a = Buffer.from(candidate);
  const b = Buffer.from(expected);
  // Compare against a fixed-length buffer first so length itself doesn't
  // leak via timingSafeEqual's own length check.
  if (a.length !== b.length) {
    timingSafeEqual(a, a); // burn constant time either way
    return false;
  }
  return timingSafeEqual(a, b);
}

export type LoginState = { error?: string } | undefined;

export async function login(_prevState: LoginState, formData: FormData): Promise<LoginState> {
  const password = String(formData.get("password") ?? "");

  if (!passwordMatches(password)) {
    return { error: "Incorrect password" };
  }

  await createSession();
  redirect("/");
}
