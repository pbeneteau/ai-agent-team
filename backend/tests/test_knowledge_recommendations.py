import json
import logging
import pytest
from fastapi.testclient import TestClient


class _FakeTextBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int = 12, output_tokens: int = 8):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, text: str, *, stop_reason: str = "end_turn"):
        self.content = [_FakeTextBlock(text)]
        self.usage = _FakeUsage()
        self.stop_reason = stop_reason


def _normalize_response_spec(item):
    if isinstance(item, dict):
        return item.get("text", ""), item.get("stop_reason", "end_turn")
    return item, "end_turn"


class _FakeMessages:
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text, stop_reason = _normalize_response_spec(next(self._responses))
        return _FakeResponse(text, stop_reason=stop_reason)


class _FakeAnthropicClient:
    def __init__(self, responses: list[str]):
        self.messages = _FakeMessages(responses)


@pytest.fixture()
def isolated_backend(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.core import usage_tracker as usage_tracker_module
    from app.core.agent_factory import get_agent_factory
    from app.core.document_store import get_document_store
    from app.core.knowledge import get_knowledge_audit_service
    from app.core.orchestrator import get_orchestrator
    from app.core.workspace import get_workspace_manager
    from app.memory.project_context import get_project_context_store
    from app.memory.skills_store import get_skills_store
    from app.memory.vector_store import get_vector_store

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-smoke")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("TEAMS_FILE", str(data_dir / "teams.json"))
    monkeypatch.setenv("WORKSPACES_DIR", str(data_dir / "workspaces"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(data_dir / "chromadb"))

    get_settings.cache_clear()
    get_agent_factory.cache_clear()
    get_document_store.cache_clear()
    get_knowledge_audit_service.cache_clear()
    get_orchestrator.cache_clear()
    get_workspace_manager.cache_clear()
    get_project_context_store.cache_clear()
    get_skills_store.cache_clear()
    get_vector_store.cache_clear()
    usage_tracker_module._tracker = None

    yield data_dir

    get_settings.cache_clear()
    get_agent_factory.cache_clear()
    get_document_store.cache_clear()
    get_knowledge_audit_service.cache_clear()
    get_orchestrator.cache_clear()
    get_workspace_manager.cache_clear()
    get_project_context_store.cache_clear()
    get_skills_store.cache_clear()
    get_vector_store.cache_clear()
    usage_tracker_module._tracker = None


@pytest.fixture()
def client(isolated_backend):
    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=True) as test_client:
        yield test_client


def test_get_agent_knowledge_recommendations_returns_readiness_payload(client: TestClient, monkeypatch):
    from app.core.knowledge import KnowledgeAuditService

    monkeypatch.setattr(KnowledgeAuditService, "_llm_audit_agent", lambda self, agent, snapshot: (None, None, None))

    agents = client.get("/api/agents/").json()
    agent_id = agents[0]["id"]

    response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")
    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == agent_id
    assert body["readiness_level"] in {"sufficient", "partial", "insufficient"}
    assert isinstance(body["recommendations"], list)
    assert body["generation_source"] in {"llm", "heuristic_fallback"}


def test_dismiss_knowledge_recommendation_persists_for_same_fingerprint(client: TestClient, monkeypatch):
    from app.core.knowledge import KnowledgeAuditService

    monkeypatch.setattr(KnowledgeAuditService, "_llm_audit_agent", lambda self, agent, snapshot: (None, None, None))

    agent_id = client.get("/api/agents/").json()[0]["id"]
    initial = client.get(f"/api/agents/{agent_id}/knowledge-recommendations").json()
    assert initial["recommendations"]

    recommendation_id = initial["recommendations"][0]["id"]
    dismissed = client.post(
        f"/api/agents/{agent_id}/knowledge-recommendations/{recommendation_id}/dismiss"
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["recommendations"][0]["status"] == "dismissed"

    refreshed = client.get(f"/api/agents/{agent_id}/knowledge-recommendations").json()
    same_recommendation = next(item for item in refreshed["recommendations"] if item["id"] == recommendation_id)
    assert same_recommendation["status"] == "dismissed"


def test_apply_research_recommendation_marks_it_applied(client: TestClient, monkeypatch):
    from app.api.routes import agents as agents_route_module
    from app.core.agent_factory import get_agent_factory
    from app.core.knowledge import KnowledgeAuditService

    monkeypatch.setenv("SERPER_API_KEY", "serper-test-key")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(KnowledgeAuditService, "_llm_audit_agent", lambda self, agent, snapshot: (None, None, None))
    monkeypatch.setattr(agents_route_module, "run_agent_research", lambda *args, **kwargs: True)

    factory = get_agent_factory()
    _, agents = factory.create_custom_team(
        name="Research Team",
        description="Test research team",
        domain="research",
        agent_specs=[
            {
                "name": "Lead",
                "title": "Research Lead",
                "specialization": "research",
                "goal": "Lead research",
                "backstory": "Lead",
                "is_lead": True,
            }
        ],
    )
    agent_id = agents[0].id
    readiness = client.get(f"/api/agents/{agent_id}/knowledge-recommendations").json()
    recommendation = next(
        item for item in readiness["recommendations"] if item["action_type"] == "launch_research"
    )

    applied = client.post(
        f"/api/agents/{agent_id}/knowledge-recommendations/{recommendation['id']}/apply"
    )
    assert applied.status_code == 200
    updated = next(item for item in applied.json()["recommendations"] if item["id"] == recommendation["id"])
    assert updated["status"] == "applied"


def test_global_knowledge_readiness_aggregates_agents(client: TestClient, monkeypatch):
    from app.core.agent_factory import get_agent_factory
    from app.core.knowledge import KnowledgeAuditService

    monkeypatch.setattr(KnowledgeAuditService, "_llm_audit_agent", lambda self, agent, snapshot: (None, None, None))

    factory = get_agent_factory()
    factory.create_custom_team(
        name="Knowledge Team",
        description="Test team",
        domain="knowledge",
        agent_specs=[
            {
                "name": "Lead",
                "title": "Knowledge Lead",
                "specialization": "strategy",
                "goal": "Coordinate",
                "backstory": "Lead",
                "is_lead": True,
            },
            {
                "name": "Specialist",
                "title": "Knowledge Specialist",
                "specialization": "research",
                "goal": "Research",
                "backstory": "Specialist",
            },
        ],
    )

    legacy_response = client.get("/api/agents/knowledge-readiness")
    assert legacy_response.status_code == 200
    legacy_body = legacy_response.json()
    assert legacy_body["total_agents"] >= 3
    assert isinstance(legacy_body["shared_gaps"], list)

    response = client.get("/api/agents/readiness/global")
    assert response.status_code == 200
    body = response.json()
    assert body["total_agents"] == legacy_body["total_agents"]
    assert body["fingerprint"] == legacy_body["fingerprint"]
    assert body["has_fallback_results"] is True
    assert body["generation_channel"] in {"heuristic_fallback", "mixed"}


def test_team_recommendations_native_path_avoids_heuristic_fallback(client: TestClient, monkeypatch):
    from app.api.routes import teams as teams_route_module

    native_json = """
    {
      "new_teams": [
        {
          "id": "capital-strategy",
          "name": "Equipe Capital Strategy",
          "description": "Structure la levee et le narratif investisseur.",
          "domain": "fundraising_strategy",
          "reason": "Le projet a besoin d'une equipe dediee a la levee.",
          "urgency": "now",
          "score": 91,
          "agents": [
            {
              "name": "Sophie",
              "title": "Fundraising Lead",
              "specialization": "fundraising",
              "goal": "Structurer la levee de fonds.",
              "backstory": "Lead fundraising early-stage.",
              "is_lead": true,
              "model_tier": "sonnet"
            }
          ]
        }
      ],
      "team_changes": []
    }
    """

    monkeypatch.setattr(
        teams_route_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=[native_json]),
    )
    monkeypatch.setattr(
        teams_route_module,
        "_heuristic_team_recommendations",
        lambda *_args, **_kwargs: pytest.fail("heuristic team fallback should not run"),
    )
    monkeypatch.setattr(
        teams_route_module,
        "_heuristic_team_change_recommendations",
        lambda *_args, **_kwargs: pytest.fail("heuristic team fallback should not run"),
    )

    response = client.get("/api/teams/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert len(body["new_teams"]) == 1
    assert body["new_teams"][0]["name"] == "Equipe Capital Strategy"
    assert body["generation_source"] == "llm"
    assert body["generation_channel"] == "native_json_schema"


def test_team_recommendations_cache_payload_uses_current_version(client: TestClient, monkeypatch):
    from app.api.routes import teams as teams_route_module

    monkeypatch.setattr(
        teams_route_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=['{"new_teams":[],"team_changes":[]}']),
    )

    response = client.get("/api/teams/recommendations")
    assert response.status_code == 200

    payload = json.loads(teams_route_module._recommendation_cache_file().read_text(encoding="utf-8"))
    assert payload["version"] == teams_route_module.RECOMMENDATION_CACHE_VERSION


def test_team_recommendations_ignores_stale_cache_before_deep_validation(client: TestClient, monkeypatch, caplog):
    from app.api.routes import teams as teams_route_module

    stale_payload = {
        "version": teams_route_module.RECOMMENDATION_CACHE_VERSION - 1,
        "fingerprint": "stale-fingerprint",
        "recommendations": {
            "new_teams": [
                {
                    "id": "capital-strategy",
                    "name": "Equipe Capital Strategy",
                    "description": "Structure la levee et le narratif investisseur.",
                    "domain": "fundraising_strategy",
                    "reason": "x" * 400,
                    "urgency": "now",
                    "score": 91,
                    "agents": [
                        {
                            "name": "Sophie",
                            "title": "Fundraising Lead",
                            "specialization": "fundraising",
                            "goal": "y" * 400,
                            "backstory": "z" * 400,
                            "is_lead": True,
                            "model_tier": "sonnet",
                        }
                    ],
                }
            ],
            "team_changes": [],
            "generation_source": "llm",
            "generation_channel": "native_json_schema",
            "generation_issue": None,
        },
    }
    teams_route_module._recommendation_cache_file().write_text(
        json.dumps(stale_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        teams_route_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=['{"new_teams":[],"team_changes":[]}']),
    )

    with caplog.at_level(logging.WARNING):
        response = client.get("/api/teams/recommendations")

    assert response.status_code == 200
    assert response.json()["generation_source"] == "llm"
    assert not any("Failed to load team recommendations cache" in message for message in caplog.messages)


def test_team_recommendations_returns_valid_cache_hit_without_calling_anthropic(client: TestClient, monkeypatch):
    from app.api.routes import teams as teams_route_module

    first_response = client.get("/api/teams/recommendations")
    assert first_response.status_code == 200

    def _unexpected_client(_api_key):
        raise AssertionError("Anthropic should not be called on cache hit")

    monkeypatch.setattr(teams_route_module, "Anthropic", _unexpected_client)

    second_response = client.get("/api/teams/recommendations")
    assert second_response.status_code == 200
    assert second_response.json() == first_response.json()


def test_team_recommendations_fallback_used_when_native_payload_is_invalid(client: TestClient, monkeypatch, caplog):
    from app.api.routes import teams as teams_route_module

    monkeypatch.setattr(
        teams_route_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=['{"new_teams":[{"id":"broken"}],"team_changes":[]}']),
    )

    with caplog.at_level(logging.WARNING):
        response = client.get("/api/teams/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_source"] == "heuristic_fallback"
    assert body["generation_channel"] == "heuristic_fallback"
    assert body["generation_issue"] is not None
    assert any("teams_recommendations fallback_used" in message for message in caplog.messages)


def test_knowledge_recommendations_native_path_avoids_heuristic_fallback(client: TestClient, monkeypatch):
    from app.core import knowledge as knowledge_module
    from app.core.knowledge import KnowledgeAuditService

    native_json = """
    {
      "readiness_level": "partial",
      "readiness_score": 62,
      "summary": "Contexte partiel mais exploitable.",
      "missing_knowledge_summary": ["Le cadrage fundraising reste incomplet."],
      "recommendations": [
        {
          "title": "Ajouter un brief fundraising",
          "summary": "L'agent manque d'un cadre investisseur.",
          "reason": "Cela aidera a mieux prioriser la preparation du deck.",
          "priority": "high",
          "knowledge_type": "internal_context",
          "action_type": "provide_document",
          "can_be_found_on_web": false,
          "recommended_source": "Brief interne fundraising",
          "suggested_topic": null,
          "evidence": [
            {
              "source_label": "project_context",
              "source_type": "project_context",
              "excerpt": "Objectif court terme encore flou."
            }
          ]
        }
      ]
    }
    """

    monkeypatch.setattr(
        knowledge_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=[native_json]),
    )
    monkeypatch.setattr(
        KnowledgeAuditService,
        "_heuristic_audit_agent",
        lambda *_args, **_kwargs: pytest.fail("heuristic knowledge fallback should not run"),
    )

    agent_id = client.get("/api/agents/").json()[0]["id"]
    response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Contexte partiel mais exploitable."
    assert len(body["recommendations"]) == 1
    assert body["generation_source"] == "llm"
    assert body["generation_channel"] == "native_json_schema"


def test_knowledge_recommendations_schema_contains_string_bounds(client: TestClient, monkeypatch):
    from app.core import knowledge as knowledge_module

    fake_client = _FakeAnthropicClient(
        responses=[
            '{"readiness_level":"sufficient","readiness_score":90,"summary":"Contexte solide.","missing_knowledge_summary":[],"recommendations":[]}'
        ]
    )
    monkeypatch.setattr(knowledge_module, "Anthropic", lambda api_key: fake_client)

    agent_id = client.get("/api/agents/").json()[0]["id"]
    response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    schema = fake_client.messages.calls[0]["output_config"]["format"]["schema"]
    assert schema["properties"]["summary"]["maxLength"] == 140
    assert schema["properties"]["missing_knowledge_summary"]["items"]["maxLength"] == 80
    recommendation_schema = schema["$defs"]["_KnowledgeAuditRecommendationPayload"]["properties"]
    evidence_schema = schema["$defs"]["_KnowledgeAuditEvidencePayload"]["properties"]
    assert recommendation_schema["title"]["maxLength"] == 60
    assert recommendation_schema["summary"]["maxLength"] == 80
    assert recommendation_schema["reason"]["maxLength"] == 140
    assert recommendation_schema["recommended_source"]["maxLength"] == 80
    assert recommendation_schema["suggested_topic"]["anyOf"][0]["maxLength"] == 120
    assert evidence_schema["excerpt"]["maxLength"] == 80


def test_knowledge_recommendations_salvage_truncated_native_json(client: TestClient, monkeypatch):
    from app.core import knowledge as knowledge_module
    from app.core.knowledge import KnowledgeAuditService

    truncated_json = (
        '{"readiness_level":"partial","readiness_score":55,"summary":"Contexte partiel mais exploitable.",'
        '"missing_knowledge_summary":["Le cadrage fundraising reste incomplet."],"recommendations":[{"title":"Ajouter un brief fundraising",'
        '"summary":"Cadre investisseur incomplet.","reason":"Aide a prioriser la preparation du deck.","priority":"high",'
        '"knowledge_type":"internal_context","action_type":"provide_document","can_be_found_on_web":false,'
        '"recommended_source":"Brief interne fundraising","suggested_topic":null,"evidence":[{"source_label":"project_context",'
        '"source_type":"project_context","excerpt":"Objectif court terme encore'
    )

    monkeypatch.setattr(
        knowledge_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(
            responses=[
                {
                    "text": truncated_json,
                    "stop_reason": "max_tokens",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        KnowledgeAuditService,
        "_heuristic_audit_agent",
        lambda *_args, **_kwargs: pytest.fail("heuristic knowledge fallback should not run"),
    )

    agent_id = client.get("/api/agents/").json()[0]["id"]
    response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_source"] == "llm"
    assert body["generation_channel"] == "native_json_schema_salvage"
    assert len(body["recommendations"]) == 1


def test_knowledge_recommendations_dense_valid_payload_stays_on_native_path(client: TestClient, monkeypatch):
    from app.core import knowledge as knowledge_module
    from app.core.knowledge import KnowledgeAuditService

    dense_payload = {
        "readiness_level": "partial",
        "readiness_score": 58,
        "summary": "a" * 130,
        "missing_knowledge_summary": ["b" * 70, "c" * 70, "d" * 70],
        "recommendations": [
            {
                "title": "t" * 50,
                "summary": "s" * 70,
                "reason": "r" * 110,
                "priority": "high",
                "knowledge_type": "internal_context",
                "action_type": "provide_document",
                "can_be_found_on_web": False,
                "recommended_source": "u" * 55,
                "suggested_topic": None,
                "evidence": [
                    {
                        "source_label": "project_context",
                        "source_type": "project_context",
                        "excerpt": "e" * 70,
                    }
                ],
            },
            {
                "title": "v" * 50,
                "summary": "w" * 70,
                "reason": "x" * 110,
                "priority": "medium",
                "knowledge_type": "market_context",
                "action_type": "launch_research",
                "can_be_found_on_web": True,
                "recommended_source": "y" * 55,
                "suggested_topic": "z" * 55,
                "evidence": [
                    {
                        "source_label": "market-note",
                        "source_type": "document",
                        "excerpt": "m" * 70,
                    }
                ],
            },
            {
                "title": "n" * 50,
                "summary": "o" * 70,
                "reason": "p" * 110,
                "priority": "low",
                "knowledge_type": "project_private",
                "action_type": "provide_document",
                "can_be_found_on_web": False,
                "recommended_source": "q" * 55,
                "suggested_topic": None,
                "evidence": [
                    {
                        "source_label": "notes",
                        "source_type": "skill",
                        "excerpt": "h" * 70,
                    }
                ],
            },
        ],
    }

    monkeypatch.setattr(
        knowledge_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=[json.dumps(dense_payload)]),
    )
    monkeypatch.setattr(
        KnowledgeAuditService,
        "_heuristic_audit_agent",
        lambda *_args, **_kwargs: pytest.fail("heuristic knowledge fallback should not run"),
    )

    agent_id = client.get("/api/agents/").json()[0]["id"]
    response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_source"] == "llm"
    assert body["generation_channel"] == "native_json_schema"
    assert len(body["recommendations"]) == 3


def test_knowledge_recommendations_accepts_longer_suggested_topic(client: TestClient, monkeypatch):
    from app.core import knowledge as knowledge_module
    from app.core.knowledge import KnowledgeAuditService

    native_payload = {
        "readiness_level": "partial",
        "readiness_score": 61,
        "summary": "Contexte partiel mais actionnable.",
        "missing_knowledge_summary": ["Quelques angles de recherche restent ouverts."],
        "recommendations": [
            {
                "title": "Comparer les attentes seed",
                "summary": "Il manque un benchmark externe actualise.",
                "reason": "Cela aidera a caler le deck et le narratif sur les attentes investisseurs actuelles.",
                "priority": "medium",
                "knowledge_type": "market_context",
                "action_type": "launch_research",
                "can_be_found_on_web": True,
                "recommended_source": "Benchmark seed et pre-seed 2026",
                "suggested_topic": "pre-seed AI infrastructure investor benchmark expectations 2026",
                "evidence": [
                    {
                        "source_label": "project_context",
                        "source_type": "project_context",
                        "excerpt": "Le positionnement investisseur manque encore de references externes.",
                    }
                ],
            }
        ],
    }

    monkeypatch.setattr(
        knowledge_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=[json.dumps(native_payload)]),
    )
    monkeypatch.setattr(
        KnowledgeAuditService,
        "_heuristic_audit_agent",
        lambda *_args, **_kwargs: pytest.fail("heuristic knowledge fallback should not run"),
    )

    agent_id = client.get("/api/agents/").json()[0]["id"]
    response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_source"] == "llm"
    assert body["generation_channel"] == "native_json_schema"
    assert body["recommendations"][0]["suggested_topic"] == native_payload["recommendations"][0]["suggested_topic"]


def test_knowledge_recommendations_sanitizes_volatile_fields_before_validation(client: TestClient, monkeypatch):
    from app.core import knowledge as knowledge_module
    from app.core.knowledge import KnowledgeAuditService

    native_payload = {
        "readiness_level": "partial",
        "readiness_score": 61,
        "summary": "Contexte partiel mais actionnable.",
        "missing_knowledge_summary": ["Quelques angles de recherche restent ouverts."],
        "recommendations": [
            {
                "title": "Comparer les attentes seed",
                "summary": "Il manque un benchmark externe actualise.",
                "reason": "r" * 170,
                "priority": "medium",
                "knowledge_type": "market_context",
                "action_type": "launch_research",
                "can_be_found_on_web": True,
                "recommended_source": "s" * 120,
                "suggested_topic": "t" * 200,
                "evidence": [
                    {
                        "source_label": "project_context",
                        "source_type": "project_context",
                        "excerpt": "e" * 120,
                    }
                ],
            }
        ],
    }

    monkeypatch.setattr(
        knowledge_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=[json.dumps(native_payload)]),
    )
    monkeypatch.setattr(
        KnowledgeAuditService,
        "_heuristic_audit_agent",
        lambda *_args, **_kwargs: pytest.fail("heuristic knowledge fallback should not run"),
    )

    agent_id = client.get("/api/agents/").json()[0]["id"]
    response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_source"] == "llm"
    assert body["generation_channel"] == "native_json_schema"
    assert len(body["recommendations"][0]["reason"]) == 140
    assert len(body["recommendations"][0]["recommended_source"]) == 80
    assert len(body["recommendations"][0]["suggested_topic"]) == 120
    assert len(body["recommendations"][0]["evidence"][0]["excerpt"]) == 80


def test_knowledge_audit_prompt_keeps_sections_under_budget(isolated_backend):
    from app.core.knowledge import KnowledgeAuditService, _PROMPT_BUDGET
    from app.models.agent import AgentConfig, AgentRole

    service = KnowledgeAuditService()
    agent = AgentConfig(
        name="Léa",
        role=AgentRole.SPECIALIST,
        title="Fundraising Analyst",
        specialization="fundraising",
        goal="g" * 500,
        backstory="b" * 500,
    )
    snapshot = {
        "project_context_summary": "p" * 5000,
        "documents": [
            {
                "filename": "deck.md",
                "description": "d" * 500,
                "excerpt": "e" * 800,
                "chunk_count": 12,
            }
            for _ in range(6)
        ],
        "skills": {f"skill_{index}": "s" * 1200 for index in range(6)},
        "research": {f"research_{index}": "r" * 1200 for index in range(4)},
    }

    prompt = service._build_audit_prompt(agent, snapshot)

    assert len(prompt) <= _PROMPT_BUDGET
    assert "## Agent" in prompt
    assert "## Project context" in prompt
    assert "## Available document summaries" in prompt
    assert "## Existing agent knowledge" in prompt


def test_knowledge_recommendations_fallback_used_when_native_payload_is_invalid(client: TestClient, monkeypatch, caplog):
    from app.core import knowledge as knowledge_module
    from app.core.knowledge import KnowledgeAuditService, _KnowledgeAuditPayload

    monkeypatch.setattr(
        knowledge_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=['{"readiness_level":"partial"}']),
    )
    monkeypatch.setattr(
        KnowledgeAuditService,
        "_heuristic_audit_agent",
        lambda self, agent, snapshot: _KnowledgeAuditPayload(
            readiness_level="partial",
            readiness_score=55,
            summary="heuristic fallback",
            missing_knowledge_summary=["gap heuristique"],
            recommendations=[],
        ),
    )

    agent_id = client.get("/api/agents/").json()[0]["id"]
    with caplog.at_level(logging.WARNING):
        response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "heuristic fallback"
    assert body["generation_source"] == "heuristic_fallback"
    assert body["generation_channel"] == "heuristic_fallback"
    assert body["generation_issue"] is not None
    assert any("knowledge_audit fallback_used" in message for message in caplog.messages)


def test_knowledge_recommendations_empty_response_retries_before_fallback(client: TestClient, monkeypatch, caplog):
    from app.core import knowledge as knowledge_module
    from app.core.knowledge import KnowledgeAuditService, _KnowledgeAuditPayload

    monkeypatch.setattr(
        knowledge_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(responses=[""]),
    )
    monkeypatch.setattr(
        KnowledgeAuditService,
        "_heuristic_audit_agent",
        lambda self, agent, snapshot: _KnowledgeAuditPayload(
            readiness_level="partial",
            readiness_score=55,
            summary="heuristic fallback after empty response",
            missing_knowledge_summary=["gap heuristique"],
            recommendations=[],
        ),
    )

    agent_id = client.get("/api/agents/").json()[0]["id"]
    with caplog.at_level(logging.WARNING):
        response = client.get(f"/api/agents/{agent_id}/knowledge-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_source"] == "heuristic_fallback"
    assert "Empty model response" in (body["generation_issue"] or "")
    assert any("empty_response=True" in message for message in caplog.messages)


def test_write_agent_skill_rejects_reserved_project_context(client: TestClient):
    agent_id = client.get("/api/agents/").json()[0]["id"]

    response = client.put(
        f"/api/agents/{agent_id}/skills/project_context",
        json={"content": "# Override", "author": "test"},
    )

    assert response.status_code == 400
    assert "reserved" in response.json()["detail"]


def test_publish_project_context_returns_published_state(client: TestClient, monkeypatch):
    from app.api.routes import teams as teams_route_module

    calls = []

    async def fake_run_project_briefing(team_id: str, _broadcast=None):
        calls.append(team_id)
        return None

    monkeypatch.setattr(teams_route_module, "run_project_briefing", fake_run_project_briefing)

    team_response = client.post(
        "/api/teams/custom",
        json={
            "name": "Context Team",
            "description": "Test team",
            "domain": "ops",
            "agents": [
                {
                    "name": "Lead",
                    "title": "Ops Lead",
                    "specialization": "coordination",
                    "goal": "Coordinate",
                    "backstory": "Lead",
                    "is_lead": True,
                }
            ],
        },
    )
    assert team_response.status_code == 200

    payload = {
        "name": "Published Project",
        "description": "Published description",
        "domain": "ops",
        "short_term_goal": "Ship beta",
    }
    response = client.post("/api/teams/project-context/publish", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["state"]["published"]["status"] == "published"
    assert body["state"]["published"]["name"] == "Published Project"
    assert body["state"]["active"]["name"] == "Published Project"
    assert len(calls) == 1


def test_team_recommendations_expose_fallback_metadata(client: TestClient, monkeypatch):
    from app.api.routes import teams as teams_route_module

    monkeypatch.setattr(
        teams_route_module,
        "Anthropic",
        lambda api_key: _FakeAnthropicClient(
            responses=[
                "",
                "",
            ]
        ),
    )

    response = client.get("/api/teams/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_source"] == "heuristic_fallback"
    assert body["generation_issue"] is not None
