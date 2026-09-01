"""Slide-intent routing and authorized presentation-outline tests."""

from __future__ import annotations

from app.rag.pipeline import Citation, RagResult
from app.rag.presentation import build_presentation_spec, is_slide_request
from tests.conftest import auth_header


def _result(question: str) -> RagResult:
    return RagResult(
        question=question,
        answer=(
            "Based on the authorized departmental documents:\n"
            "- Technical review is required before approval. [C1]"
        ),
        citations=[
            Citation(
                citation_id="C1",
                document_id="doc-1",
                title="Engineering Approval Policy",
                page=2,
                section="Review",
            )
        ],
        evidence_status="sufficient",
        documents_used=["doc-1"],
        evidence=[
            {
                "citation_id": "C1",
                "document_id": "doc-1",
                "document_title": "Engineering Approval Policy",
                "page": 2,
                "section": "Review",
                "text": "Technical review is required before approval.",
            },
            {
                "citation_id": "C2",
                "document_id": "unauthorized-for-output",
                "document_title": "Unvalidated Retrieval",
                "page": None,
                "section": None,
                "text": "UNVALIDATED PRESENTATION SECRET",
            },
        ],
    )


def test_slide_intent_requires_creation_language():
    assert is_slide_request("Create a 5-slide presentation about approvals")
    assert is_slide_request("Slides about the procurement policy")
    assert not is_slide_request("What is a PowerPoint presentation?")
    assert not is_slide_request("Explain the procurement policy")


def test_presentation_uses_only_validated_citations():
    question = "Create a 5-slide presentation about engineering approvals"
    spec = build_presentation_spec(question, _result(question))

    assert spec is not None
    assert spec.kind == "pptx"
    assert spec.filename.endswith(".pptx")
    assert spec.slide_count == len(spec.slides) + 1
    serialized = spec.model_dump_json()
    assert "Technical review is required" in serialized
    assert "UNVALIDATED PRESENTATION SECRET" not in serialized
    assert "C2" not in serialized


def test_presentation_can_use_labelled_general_knowledge():
    question = "Create a 5-slide presentation about photosynthesis"
    result = RagResult(
        question=question,
        answer=(
            "No relevant authorized document was found. The following answer is based on "
            "general model knowledge and may be incomplete or outdated.\n\n"
            "- Definition: Plants convert light energy into chemical energy.\n"
            "- Inputs: Carbon dioxide, water, and light are required.\n"
            "- Outputs: Glucose and oxygen are produced.\n"
            "- Importance: The process supports most food chains."
        ),
        evidence_status="insufficient",
        answer_source="general_knowledge",
    )

    spec = build_presentation_spec(question, result)

    assert spec is not None
    assert spec.source_mode == "general_knowledge"
    assert spec.slide_count == 5
    assert spec.slides[-1].title == "About this content"
    assert not any(slide.source_ids for slide in spec.slides)
    assert "Evidence unavailable" not in spec.model_dump_json()


def test_presentation_strips_markdown_from_slide_text():
    """Markdown (###, **bold**) must never appear literally in slide text."""
    question = "Create a 4-slide presentation about the deployment process"
    result = RagResult(
        question=question,
        answer=(
            "No relevant authorized document was found. General knowledge follows.\n\n"
            "### Steps in the Deployment Process\n"
            "**Planning**: Define objectives, scope, and timeline.\n"
            "**Execution**: Run the release with a rollback plan."
        ),
        evidence_status="insufficient",
        answer_source="general_knowledge",
    )

    spec = build_presentation_spec(question, result)
    assert spec is not None
    blob = spec.model_dump_json()
    assert "###" not in blob
    assert "**" not in blob
    for slide in spec.slides:
        assert "#" not in slide.title and "*" not in slide.title


def test_rag_route_activates_presentation_for_slide_requests(
    client, make_user, token_for, monkeypatch
):
    make_user("slides@example.com")
    token = token_for("slides@example.com")
    question = "Generate a 4-slide deck about engineering approvals"

    monkeypatch.setattr("app.routes.rag.run_agentic_query", lambda *args, **kwargs: _result(question))

    response = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": question},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["presentation"]["kind"] == "pptx"
    assert body["presentation"]["slide_count"] >= 3
    assert "UNVALIDATED PRESENTATION SECRET" not in str(body["presentation"])

    normal = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": "Explain engineering approvals"},
    )
    assert normal.status_code == 200
    assert "presentation" not in normal.json()
