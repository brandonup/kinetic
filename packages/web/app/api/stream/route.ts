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

  const conversationId = searchParams.get("conversation_id");
  if (!conversationId) {
    return new Response("Missing conversation_id", { status: 400 });
  }

  const content = searchParams.get("content");
  if (!content) {
    return new Response("Missing content", { status: 400 });
  }

  const modelId = searchParams.get("model_id");
  const agentInstanceId = searchParams.get("agent_instance_id");

  // POST to FastAPI generation endpoint (EventSource only supports GET,
  // so this proxy translates GET → POST and injects the JWT).
  const backendUrl = `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages`;

  const body: Record<string, string> = { content };
  if (modelId) body.model_id = modelId;
  if (agentInstanceId) body.agent_instance_id = agentInstanceId;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (effectiveToken) {
    headers["Authorization"] = `Bearer ${effectiveToken}`;
  }

  const backendRes = await fetch(backendUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

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
