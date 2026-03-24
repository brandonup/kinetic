/**
 * ChatThread + ChatMessage + AgentSwitchMarker + CitationPanel tests — KIN-337
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ChatThread } from "@/components/ChatThread";
import type { ChatMessageData } from "@/components/ChatMessage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMsg(overrides: Partial<ChatMessageData> & { id: string }): ChatMessageData {
  return {
    role: "assistant",
    content: "Hello",
    agent_definition_id: null,
    agent_name: null,
    model: null,
    citations: [],
    created_at: "2026-03-24T12:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// ChatThread
// ---------------------------------------------------------------------------

describe("ChatThread", () => {
  it("renders empty state when no messages", () => {
    render(<ChatThread messages={[]} />);
    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
  });

  it("renders user and assistant messages", () => {
    const messages: ChatMessageData[] = [
      makeMsg({ id: "1", role: "user", content: "What is strategy?" }),
      makeMsg({ id: "2", role: "assistant", content: "Strategy is a plan of action." }),
    ];
    render(<ChatThread messages={messages} />);
    expect(screen.getByText("What is strategy?")).toBeInTheDocument();
    expect(screen.getByText("Strategy is a plan of action.")).toBeInTheDocument();
  });

  it("shows agent badge on assistant message when agent is active", () => {
    const messages: ChatMessageData[] = [
      makeMsg({
        id: "1",
        role: "assistant",
        content: "I am Nate.",
        agent_definition_id: "agent-1",
        agent_name: "Nate",
      }),
    ];
    render(<ChatThread messages={messages} />);
    expect(screen.getByText("Nate")).toBeInTheDocument();
  });

  it("shows model label on assistant message", () => {
    const messages: ChatMessageData[] = [
      makeMsg({
        id: "1",
        role: "assistant",
        content: "Response",
        model: "claude-sonnet-4-6",
      }),
    ];
    render(<ChatThread messages={messages} />);
    expect(screen.getByText("claude-sonnet-4-6")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Agent switch markers
// ---------------------------------------------------------------------------

describe("AgentSwitchMarker in ChatThread", () => {
  it("shows marker when agent changes between assistant messages", () => {
    const messages: ChatMessageData[] = [
      makeMsg({
        id: "1",
        role: "assistant",
        content: "From Nate",
        agent_definition_id: "agent-1",
        agent_name: "Nate",
      }),
      makeMsg({ id: "2", role: "user", content: "Switch agent" }),
      makeMsg({
        id: "3",
        role: "assistant",
        content: "From Alex",
        agent_definition_id: "agent-2",
        agent_name: "Alex",
      }),
    ];
    render(<ChatThread messages={messages} />);
    expect(screen.getByText("Switched to Alex")).toBeInTheDocument();
  });

  it("shows 'Agent disconnected' when agent goes null", () => {
    const messages: ChatMessageData[] = [
      makeMsg({
        id: "1",
        role: "assistant",
        content: "With agent",
        agent_definition_id: "agent-1",
        agent_name: "Nate",
      }),
      makeMsg({
        id: "2",
        role: "assistant",
        content: "No agent",
        agent_definition_id: null,
        agent_name: null,
      }),
    ];
    render(<ChatThread messages={messages} />);
    expect(screen.getByText("Agent disconnected")).toBeInTheDocument();
  });

  it("does not show marker when same agent continues", () => {
    const messages: ChatMessageData[] = [
      makeMsg({
        id: "1",
        role: "assistant",
        content: "First",
        agent_definition_id: "agent-1",
        agent_name: "Nate",
      }),
      makeMsg({
        id: "2",
        role: "assistant",
        content: "Second",
        agent_definition_id: "agent-1",
        agent_name: "Nate",
      }),
    ];
    render(<ChatThread messages={messages} />);
    expect(screen.queryByText(/switched to/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Citations
// ---------------------------------------------------------------------------

describe("Citations in ChatThread", () => {
  const messagesWithCitations: ChatMessageData[] = [
    makeMsg({
      id: "1",
      role: "assistant",
      content: "Based on the documents...",
      citations: [
        {
          chunk_id: "c1",
          document_title: "Strategy Guide",
          text_preview: "A strategy is a long-term plan...",
          score: 0.87,
        },
        {
          chunk_id: "c2",
          document_title: "Business Ops Manual",
          text_preview: "Operational efficiency requires...",
          score: 0.72,
        },
      ],
    }),
  ];

  it("shows citation count button (collapsed by default)", () => {
    render(<ChatThread messages={messagesWithCitations} />);
    expect(screen.getByText("2 sources")).toBeInTheDocument();
    // Citations not visible before expand
    expect(screen.queryByText("Strategy Guide")).not.toBeInTheDocument();
  });

  it("expands citations on click", async () => {
    const user = userEvent.setup();
    render(<ChatThread messages={messagesWithCitations} />);

    await user.click(screen.getByText("2 sources"));

    expect(screen.getByText("Strategy Guide")).toBeInTheDocument();
    expect(screen.getByText("Business Ops Manual")).toBeInTheDocument();
    expect(screen.getByText("87% match")).toBeInTheDocument();
    expect(screen.getByText("72% match")).toBeInTheDocument();
  });

  it("does not render citation panel when no citations", () => {
    const messages: ChatMessageData[] = [
      makeMsg({ id: "1", role: "assistant", content: "No sources here" }),
    ];
    render(<ChatThread messages={messages} />);
    expect(screen.queryByText(/\d+ sources?/i)).not.toBeInTheDocument();
  });
});
