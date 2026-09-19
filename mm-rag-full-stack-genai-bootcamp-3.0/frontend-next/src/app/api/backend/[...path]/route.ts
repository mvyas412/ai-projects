import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { hasTrustedMutationOrigin, isAllowedBackendRoute } from "@/lib/backend-policy";

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const segments = (await context.params).path;
  const backendPath = `/api/v1/${segments.join("/")}`;
  if (!isAllowedBackendRoute(request.method, backendPath)) {
    return NextResponse.json({ detail: "Route not available" }, { status: 404 });
  }
  const appBaseUrl = process.env.APP_BASE_URL;
  if (
    request.method !== "GET" &&
    (!appBaseUrl || !hasTrustedMutationOrigin(appBaseUrl, request.headers.get("origin")))
  ) {
    return NextResponse.json({ detail: "Request origin rejected" }, { status: 403 });
  }

  const session = await auth0.getSession();
  if (!session) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }
  const { token } = await auth0.getAccessToken();
  const backendUrl = new URL(backendPath, process.env.MM_RAG_INTERNAL_API_URL ?? "http://api:8003");
  backendUrl.search = request.nextUrl.search;

  const headers = new Headers({ Authorization: `Bearer ${token}`, Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  const idempotencyKey = request.headers.get("idempotency-key");
  if (contentType) headers.set("content-type", contentType);
  if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);

  const response = await fetch(backendUrl, {
    method: request.method,
    headers,
    body: request.method === "GET" ? undefined : await request.arrayBuffer(),
    cache: "no-store",
    signal: AbortSignal.timeout(180_000),
  });
  const responseType = response.headers.get("content-type") ?? "application/json";
  return new NextResponse(await response.arrayBuffer(), {
    status: response.status,
    headers: { "content-type": responseType, "cache-control": "no-store" },
  });
}

export const GET = forward;
export const POST = forward;
