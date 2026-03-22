import { NextRequest } from "next/server";
import { cookies } from "next/headers";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);

  // Extract access token from query param (EventSource cannot send headers)
  const accessToken = searchParams.get("access_token");
  const cookieTokenFromReq = (req as any)?.cookies?.get?.(
    "sb-access-token"
  )?.value as string | undefined;
  let cookieTokenFromNextHeaders: string | undefined;
  try {
    cookieTokenFromNextHeaders = cookies().get("sb-access-token")?.value;
  } catch {
    cookieTokenFromNextHeaders = undefined;
  }
  const effectiveToken =
    accessToken || cookieTokenFromReq || cookieTokenFromNextHeaders;

  // Forward to Kinetic FastAPI chat stream endpoint
  const backendParams = new URLSearchParams(searchParams);
  backendParams.delete("access_token");
  const backendUrl = `${API_BASE_URL}/api/v1/chat/stream?${backendParams.toString()}`;

  const headers: HeadersInit = { Accept: "text/event-stream" };
  if (effectiveToken) {
    headers["Authorization"] = `Bearer ${effectiveToken}`;
  }

  const backendRes = await fetch(backendUrl, { method: "GET", headers });

  if (!backendRes.ok || !backendRes.body) {
    const text = await backendRes.text();
    return new Response(text, { status: backendRes.status });
  }

  const stream = new ReadableStream({
    async start(controller) {
      const reader = backendRes.body!.getReader();
      // Immediate ping keeps EventSource alive while backend prepares
      controller.enqueue(new TextEncoder().encode(": ping\n\n"));
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            controller.close();
            break;
          }
          controller.enqueue(value);
        }
      } catch (e) {
        controller.error(e);
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
