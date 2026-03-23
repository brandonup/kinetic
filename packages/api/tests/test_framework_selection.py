"""
Tests for Framework Selection Pipeline — KIN-290 / KIN-297.

Scaffolded by Jìan (KIN-297). Activated by KIN-293 once Big Head ships KIN-290.

4-step pipeline (ADR-005 / docs/adr-003-agents-architecture.md):
  Step 1 — Embed user query → cosine similarity against trigger_embeddings per agent
  Step 2 — Expertise boost + recency boost (tie-breaking)
  Step 3 — Haiku reranker on top-5 candidates (~50 output tokens, platform key)
  Step 4 — Inject winner whole into context (Layer 7). No match → no injection.

Schema refs:
  - db-schema-spec.md §14 (frameworks)
  - db-schema-spec.md §15 (framework_trigger_embeddings)
"""

import pytest

SKIP_REASON = "Blocked — waiting for KIN-290 (Big Head framework selection pipeline)"


# ---------------------------------------------------------------------------
# Trigger embedding generation (at framework create/update time)
# ---------------------------------------------------------------------------

class TestTriggerEmbeddingGeneration:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_trigger_embeddings_created_when_framework_added(self, auth_client):
        """Creating a framework generates one trigger embedding row per when_to_apply phrase."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_trigger_embedding_count_matches_when_to_apply_count(self, auth_client):
        """If a framework has 4 trigger phrases, exactly 4 embedding rows are created."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_trigger_embeddings_deleted_when_framework_deleted(self, auth_client):
        """Deleting a framework cascades to its trigger_embeddings rows."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_trigger_embeddings_regenerated_when_triggers_updated(self, auth_client):
        """Updating when_to_apply replaces all existing trigger embeddings for that framework."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_embedding_model_recorded_on_trigger_row(self, auth_client):
        """Each trigger embedding row records the embedding model used."""
        ...


# ---------------------------------------------------------------------------
# Step 1 — Cosine similarity search
# ---------------------------------------------------------------------------

class TestCosineSimilaritySearch:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_relevant_query_returns_matching_framework(self, auth_client):
        """A query semantically similar to a trigger phrase returns the expected framework."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_search_scoped_to_agent(self, auth_client):
        """Framework selection only searches trigger_embeddings for the active agent — not all agents."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_no_match_returns_empty(self, auth_client):
        """A query with no semantic match returns no candidate frameworks."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_similarity_threshold_filters_low_score_candidates(self, auth_client):
        """Candidates below the similarity threshold are not passed to the reranker."""
        ...


# ---------------------------------------------------------------------------
# Step 2 — Expertise + recency boost
# ---------------------------------------------------------------------------

class TestExpertiseBoost:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_high_confidence_framework_boosted_over_medium(self, auth_client):
        """When similarity scores are equal, high-confidence framework ranks above medium-confidence."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_pinned_framework_prioritized(self, auth_client):
        """Frameworks in AgentInstance.framework_overrides.pinned are always included in top candidates."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_excluded_framework_not_returned(self, auth_client):
        """Frameworks in AgentInstance.framework_overrides.excluded are removed before reranking."""
        ...


# ---------------------------------------------------------------------------
# Step 3 — Haiku reranker
# ---------------------------------------------------------------------------

class TestHaikuReranker:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_reranker_called_with_top_5_candidates(self, auth_client):
        """At most 5 candidates are passed to the Haiku reranker call."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_reranker_uses_platform_key_not_byok(self, auth_client):
        """Haiku reranker call uses platform key — does not require user BYOK."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_reranker_output_is_single_winner_or_none(self, auth_client):
        """Reranker outputs a single framework to inject, or None if no good match."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_reranker_token_budget_approx_50_output_tokens(self, auth_client):
        """Haiku reranker call is constrained to ~50 output tokens."""
        ...


# ---------------------------------------------------------------------------
# Step 4 — Injection into context (Layer 7)
# ---------------------------------------------------------------------------

class TestFrameworkInjection:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_winner_injected_whole_into_layer_7(self, auth_client):
        """The winning framework is injected whole (all fields) at Layer 7 position in context."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_no_injection_when_no_match(self, auth_client):
        """When pipeline returns no winner, Layer 7 is absent from the context stack."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_only_one_framework_injected_per_query(self, auth_client):
        """Exactly zero or one framework is injected — never more than one."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_framework_not_injected_when_no_agent_active(self, auth_client):
        """Framework selection pipeline does not run when active_agent_id is null."""
        ...


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

class TestFrameworkSelectionIntegration:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_end_to_end_relevant_query_injects_correct_framework(self, auth_client):
        """Full pipeline: known query → expected framework in assembled context."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_end_to_end_irrelevant_query_no_injection(self, auth_client):
        """Full pipeline: irrelevant query → no framework injected."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_pinned_framework_injected_regardless_of_similarity(self, auth_client):
        """Pinned frameworks bypass similarity check — always reach reranker."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_pipeline_returns_retrieval_debug_log_row(self, auth_client, admin_client):
        """After each query with active agent, a retrieval_debug_logs row is written."""
        ...
