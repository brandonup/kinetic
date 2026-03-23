"""
Tests for Context Stack Assembly — KIN-275 / KIN-291 / KIN-296 / KIN-297.

Scaffolded by Jìan (KIN-296 Sprint 3, KIN-297 Sprint 4).
- Sprint 3 stubs (KIN-275): Activated by KIN-279 once Big Head ships KIN-275.
- Sprint 4 agent layer stubs (KIN-291): Activated by KIN-293 once Big Head ships KIN-291.

Spec refs:
  - docs/specs/kin-257-projects-conversations-spec.md §2.5 (scoping rules)
  - docs/prd.md §10 (9-layer context stack)
  - docs/adr-003-agents-architecture.md (agent layer architecture)

Layer summary (Sprint 3 — Layers 1–4 + 8 only):
  L1 — User bio (always)
  L2 — Company description (always)
  L3 — Project instructions (project conversations only)
  L4 — Project Active Memory (stub — empty until Sprint 5)
  L5 — Agent system prompt (Sprint 4 — skip)
  L6 — Agent Active Memory (Sprint 5 — skip)
  L7 — Matched framework (Sprint 4 — skip)
  L8 — Project KB RAG (project conversations only)
  L9 — Agent KB RAG (Sprint 4 — skip)
"""

import pytest

SKIP_REASON = "Blocked — waiting for KIN-275 (Big Head context stack implementation)"


# ---------------------------------------------------------------------------
# Unit tests — assemble() function
# ---------------------------------------------------------------------------

class TestLayerPresenceProjectConversation:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l1_user_bio_always_included(self):
        """Layer 1 (user bio) must appear in assembled context for project conversations."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l2_company_description_always_included(self):
        """Layer 2 (company description) must appear in assembled context."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l3_project_instructions_included_for_project_conv(self):
        """Layer 3 (project instructions) injected when conversation has project_id set."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l4_active_memory_stub_returns_empty_in_sprint3(self):
        """Layer 4 (project active memory) is a stub in Sprint 3 — contributes empty string."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l8_kb_rag_included_for_project_conv(self):
        """Layer 8 (KB RAG) injected for project conversations when docs are indexed."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l8_kb_rag_below_threshold_not_injected(self):
        """Layer 8 chunks below similarity threshold (0.3) must not be injected."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_layer_ordering_l1_before_l2_before_l3(self):
        """Layers must appear in ascending order: L1, L2, L3, L4, history, L8."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_agent_layers_absent_when_no_agent_invoked(self):
        """L5, L6, L7, L9 must not appear in Sprint 3 output (agent layers stub)."""
        ...


class TestLayerPresenceCompanyConversation:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l1_user_bio_included(self):
        """Layer 1 included for company-level conversations."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l2_company_description_included(self):
        """Layer 2 included for company-level conversations."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l3_project_instructions_excluded(self):
        """Layer 3 must NOT appear when conversation has no project_id."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l4_active_memory_excluded(self):
        """Layer 4 must NOT appear for company-level conversations."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l8_kb_rag_excluded(self):
        """Layer 8 (project KB) must NOT appear for company-level conversations."""
        ...


class TestTokenBudget:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_rag_max_tokens_is_15_percent_of_context_window(self):
        """RAG_MAX_TOKENS = ceil(model.context_window * 0.15), floor at 2048."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_rag_token_budget_floor_at_2048(self):
        """Even if 15% of context_window < 2048, floor is 2048 tokens."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_chunks_filled_greedily_by_similarity_score(self):
        """RAG budget filled greedily from highest-similarity chunks across all scopes."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_context_stack_does_not_exceed_model_context_window(self):
        """Total assembled context + conversation history must not exceed model limit."""
        ...


class TestConversationHistoryInjection:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_recent_messages_injected_verbatim(self):
        """Most recent N messages injected verbatim between context layers and query."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_summary_injected_when_compression_active(self):
        """When a conversation_summaries row exists, inject summary instead of compressed messages."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_system_messages_excluded_from_history_injection(self):
        """Role=system messages are never injected into the context sent to the LLM."""
        ...


class TestContextStackIntegration:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_assemble_project_conversation_full_stack(self, auth_client):
        """End-to-end: project conversation assembles L1+L2+L3+history+L8 in correct order."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_assemble_company_conversation_layers_1_2_only(self, auth_client):
        """End-to-end: company conversation assembles L1+L2+history only."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_empty_user_bio_layer_1_still_present_but_empty(self, auth_client):
        """L1 is always injected even if user.bio is null/empty."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_empty_company_description_layer_2_still_present(self, auth_client):
        """L2 is always injected even if company.description is null."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_null_project_instructions_layer_3_excluded(self, auth_client):
        """If project.instructions is null, L3 is omitted entirely (not injected as empty)."""
        ...


# ---------------------------------------------------------------------------
# Sprint 4 — Agent layers (L5–L7 + L9)  KIN-291
# ---------------------------------------------------------------------------

SKIP_AGENT_LAYERS = "Blocked — waiting for KIN-291 (Big Head agent context layers, Sprint 4)"


class TestAgentLayerPresence:
    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l5_agent_system_prompt_injected_when_agent_active(self):
        """Layer 5 (agent instructions) present in context when active_agent_id is set."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l5_absent_when_no_agent(self):
        """Layer 5 must not appear when active_agent_id is null."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l6_agent_active_memory_injected_when_agent_active(self):
        """Layer 6 (agent instance active memory) injected when agent is active and memory non-empty."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l6_absent_when_active_memory_null(self):
        """Layer 6 omitted entirely when AgentInstance.active_memory is null."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l7_framework_injected_on_strong_match(self):
        """Layer 7 (matched framework) present when framework selection pipeline returns a winner."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l7_absent_when_no_framework_match(self):
        """Layer 7 absent when framework selection pipeline returns no winner."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l9_agent_kb_rag_injected_when_agent_has_kb(self):
        """Layer 9 (agent KB RAG) injected when agent has a KB and similarity threshold met."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_l9_absent_when_agent_has_no_kb(self):
        """Layer 9 absent when AgentDefinition has no knowledge_base_id."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_agent_layers_absent_in_company_conversation_without_agent(self):
        """L5–L7+L9 must not appear for company-level conversations with no agent active."""
        ...


class TestAgentLayerOrdering:
    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_full_project_conversation_layer_order_with_agent(self):
        """Full order: L1, L2, L3, L4, L5, L6, L7, history, L8, L9 (per spec §2.5)."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_full_company_conversation_layer_order_with_agent(self):
        """Company-level: L1, L2, L5, L6, L7, history, L9 — no L3/L4/L8."""
        ...


class TestAgentLayerSwitchBehavior:
    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_switching_agent_replaces_l5_l6_l7_l9(self):
        """After switching agents, new agent's layers replace previous agent's layers immediately."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_deactivating_agent_removes_all_agent_layers(self):
        """After active_agent_id set to null, L5–L7+L9 must not appear in context."""
        ...

    @pytest.mark.skip(reason=SKIP_AGENT_LAYERS)
    def test_each_agents_instance_memory_independent(self):
        """Switching from agent A to agent B: L6 uses agent B's instance memory, not A's."""
        ...
