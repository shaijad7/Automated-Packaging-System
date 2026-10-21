import { NextRequest, NextResponse } from "next/server";

function getValidatedApiOrigin(isDev: boolean): string | null {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return isDev ? "http://localhost:8000" : null;
  }

  try {
    const parsed = new URL(apiUrl);

    // Validate protocol scheme
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      console.warn("Invalid NEXT_PUBLIC_API_URL protocol scheme; omitting from CSP connect-src.");
      return isDev ? "http://localhost:8000" : null;
    }

    // Reject embedded credentials
    if (parsed.username || parsed.password) {
      console.warn("Credentials detected in NEXT_PUBLIC_API_URL; omitting from CSP connect-src.");
      return isDev ? "http://localhost:8000" : null;
    }

    const isLocalhost =
      parsed.hostname === "localhost" ||
      parsed.hostname === "127.0.0.1" ||
      parsed.hostname === "::1" ||
      parsed.hostname === "[::1]";

    // In production, reject unencrypted HTTP unless targeting local loopback
    if (!isDev && parsed.protocol === "http:" && !isLocalhost) {
      console.warn("Insecure HTTP API URL configured for production; omitting from CSP connect-src.");
      return null;
    }

    return parsed.origin;
  } catch {
    console.warn("Malformed NEXT_PUBLIC_API_URL; omitting from CSP connect-src.");
    return isDev ? "http://localhost:8000" : null;
  }
}

export function proxy(request: NextRequest) {
  const isDev = process.env.NODE_ENV !== "production";

  // Generate cryptographically unpredictable per-request nonce
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");

  // connect-src: strictly 'self' and validated API origin (no wildcard https:)
  const connectOrigins = ["'self'"];
  const apiOrigin = getValidatedApiOrigin(isDev);
  if (apiOrigin && !connectOrigins.includes(apiOrigin)) {
    connectOrigins.push(apiOrigin);
  }

  // Permit localhost strictly for local development tooling
  if (isDev && !connectOrigins.includes("http://localhost:8000")) {
    connectOrigins.push("http://localhost:8000");
  }

  // Production script-src contains NO unsafe-inline and NO unsafe-eval
  const scriptSrc = isDev
    ? `'self' 'unsafe-eval' 'nonce-${nonce}'`
    : `'self' 'nonce-${nonce}'`;

  const directives: [string, string][] = [
    ["default-src", "'self'"],
    ["script-src", scriptSrc],
    ["style-src", "'self' 'unsafe-inline'"],
    ["img-src", "'self' data: blob:"],
    ["font-src", "'self' data:"],
    ["connect-src", connectOrigins.join(" ")],
    ["object-src", "'none'"],
    ["base-uri", "'self'"],
    ["form-action", "'self'"],
    ["frame-ancestors", "'none'"],
  ];

  const cspHeader = directives
    .map(([name, val]) => `${name} ${val}`)
    .join("; ");

  // Forward nonce and CSP to Next.js rendering pipeline via request headers
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", cspHeader);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  // Set CSP on outgoing response to client browser
  response.headers.set("Content-Security-Policy", cspHeader);

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, icon.svg (metadata files)
     */
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|icon.svg).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
