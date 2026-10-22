import { type NextRequest, NextResponse } from "next/server";

/**
 * Optimistic auth redirect: if there is no Django session cookie at all, send the
 * visitor to sign-in before rendering. This is a UX shortcut only; the API enforces
 * authentication and authorization on every request.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has("sessionid")) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/o/:path*", "/orgs/:path*", "/account", "/oauth/:path*"],
};
