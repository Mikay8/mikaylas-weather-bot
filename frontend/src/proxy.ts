import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { COOKIE_NAME, verifySessionToken } from "@/lib/session";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (DEMO_MODE) {
    // Demo deployment is intentionally public (no login) — it's read-only,
    // enforced both by hiding controls in the UI and by the API rejecting
    // mutating requests from this origin. /settings has no read-only value
    // (data pipeline internals, wallet reset, cron triggers), so it's
    // blocked outright rather than partially rendered.
    if (pathname === "/settings" || pathname.startsWith("/settings/")) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
  }

  if (pathname === "/login") {
    return NextResponse.next();
  }

  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!verifySessionToken(token)) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
