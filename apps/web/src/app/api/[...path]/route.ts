const UPSTREAM_API_BASE = (
  process.env.INTERNAL_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000"
).replace(/\/$/, "");

const REQUEST_HEADERS = [
  "accept",
  "authorization",
  "content-type",
  "idempotency-key",
  "if-match",
  "last-event-id",
  "traceparent",
  "x-dev-user-email",
  "x-dev-user-name",
  "x-dev-user-subject",
  "x-request-id",
] as const;

const RESPONSE_HEADERS = [
  "cache-control",
  "content-disposition",
  "content-type",
  "etag",
  "idempotency-replayed",
  "x-request-id",
] as const;

type RouteContext = { params: Promise<{ path: string[] }> };

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function copyAllowedHeaders(source: Headers, names: readonly string[]) {
  const result = new Headers();
  for (const name of names) {
    const value = source.get(name);
    if (value !== null) result.set(name, value);
  }
  return result;
}

async function proxy(request: Request, context: RouteContext) {
  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const upstreamPath = path.map(encodeURIComponent).join("/");
  const upstreamUrl = `${UPSTREAM_API_BASE}/${upstreamPath}${incomingUrl.search}`;
  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : await request.arrayBuffer();

  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: copyAllowedHeaders(request.headers, REQUEST_HEADERS),
      body,
      cache: "no-store",
      redirect: "manual",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: copyAllowedHeaders(upstream.headers, RESPONSE_HEADERS),
    });
  } catch {
    return Response.json(
      {
        code: "bff_upstream_unavailable",
        detail: "API 连接暂时不可用，请稍后重试。",
      },
      { status: 502 },
    );
  }
}

export async function GET(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export async function HEAD(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export async function POST(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export async function PUT(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export async function PATCH(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export async function DELETE(request: Request, context: RouteContext) {
  return proxy(request, context);
}
