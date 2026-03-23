import { NextRequest } from "next/server";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);

  // Extract access token: query param takes precedence (EventSource cannot send headers),
  // fallback to cookie set by Supabase auth-helpers middleware.
  const accessToken = searchParams.get("access_token");
  const cookieToken = req.cookies.get("sb-access-token")?.value;
  const effectiveToken = accessToken || cookieToken;

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
