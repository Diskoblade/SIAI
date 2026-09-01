"""Scientific fluids-tool routing, validation, and API provenance tests."""

from __future__ import annotations

import pytest

from app.agent_tools import fluids_tool
from app.agent_tools.fluids_tool import (
    execute_fluids_calculation,
    is_fluids_calculation_request,
    run_fluids_tool,
)
from tests.conftest import auth_header


def _output(result, key: str) -> float:
    return next(item.value for item in result.outputs if item.key == key)


def test_reynolds_calculation_uses_fluids_library():
    result = execute_fluids_calculation(
        "reynolds_number",
        {
            "velocity": 2.0,
            "diameter": 0.05,
            "density": 998.0,
            "dynamic_viscosity": 0.001,
        },
    )

    assert result.success is True
    assert result.tool == "fluids"
    assert result.library_version == "1.3.1"
    assert _output(result, "reynolds_number") == pytest.approx(99800.0)
    assert result.notes == ["Flow regime: turbulent."]


def test_pipe_pressure_drop_returns_intermediate_engineering_values():
    result = execute_fluids_calculation(
        "pipe_pressure_drop",
        {
            "velocity": 2.0,
            "diameter": 0.05,
            "length": 10.0,
            "density": 998.0,
            "dynamic_viscosity": 0.001,
            "roughness": 0.000005,
        },
    )

    assert result.success is True
    assert _output(result, "darcy_friction_factor") == pytest.approx(0.0185207961)
    assert _output(result, "pressure_drop") == pytest.approx(7393.5018)


@pytest.mark.parametrize(
    ("operation", "arguments", "output_key", "expected"),
    [
        ("friction_factor", {"reynolds_number": 100000.0, "relative_roughness": 0.0001}, "darcy_friction_factor", 0.0185138661),
        ("loss_pressure_drop", {"loss_coefficient": 4.0, "density": 1000.0, "velocity": 3.0}, "pressure_drop", 18000.0),
        ("froude_number", {"velocity": 3.0, "characteristic_length": 2.0}, "froude_number", 0.6774011336),
        ("mach_number", {"velocity": 343.0, "speed_of_sound": 343.0}, "mach_number", 1.0),
        ("weber_number", {"velocity": 2.0, "characteristic_length": 0.01, "density": 1000.0, "surface_tension": 0.072}, "weber_number", 555.5555556),
        ("cavitation_number", {"pressure": 101325.0, "vapor_pressure": 2339.0, "density": 998.0, "velocity": 5.0}, "cavitation_number", 7.9347495),
    ],
)
def test_allow_listed_operations(operation, arguments, output_key, expected):
    result = execute_fluids_calculation(operation, arguments)

    assert result.success is True
    assert _output(result, output_key) == pytest.approx(expected, rel=1e-6)


def test_router_requires_explicit_calculation_intent():
    assert is_fluids_calculation_request("Calculate the Reynolds number for this flow")
    assert not is_fluids_calculation_request("What is the Reynolds number?")
    assert not is_fluids_calculation_request("Calculate the annual procurement total")


def test_offline_router_extracts_labelled_si_values():
    result = run_fluids_tool(
        "Calculate Reynolds number for velocity 2 m/s, diameter 0.05 m, "
        "density 998 kg/m3, and dynamic viscosity 0.001 Pa*s."
    )

    assert result is not None and result.success is True
    assert _output(result, "reynolds_number") == pytest.approx(99800.0)


def test_llm_can_select_tool_but_not_an_arbitrary_function(monkeypatch):
    class _UnsafeReasoner:
        available = True

        def complete_json(self, system, user, default):
            return {
                "use_tool": True,
                "operation": "__import__",
                "arguments": {"expression": "open('/etc/passwd').read()"},
            }

    monkeypatch.setattr(fluids_tool, "get_reasoner", lambda: _UnsafeReasoner())
    result = run_fluids_tool("Calculate the Reynolds number for this fluid flow")

    assert result is not None
    assert result.operation == "reynolds_number"
    assert result.success is False
    assert "Missing required inputs" in result.error


def test_invalid_or_missing_values_fail_without_executing_arbitrary_code():
    unsupported = execute_fluids_calculation(
        "eval", {"velocity": 1.0, "expression": "1 + 1"}
    )
    invalid = execute_fluids_calculation(
        "mach_number", {"velocity": float("inf"), "speed_of_sound": 343.0}
    )

    assert unsupported.success is False
    assert unsupported.error == "This fluids operation is not supported."
    assert invalid.success is False
    assert "finite" in invalid.error


def test_rag_api_activates_fluids_and_returns_structured_provenance(
    client, make_user, token_for
):
    make_user("engineer@example.com")
    response = client.post(
        "/api/rag/query",
        headers=auth_header(token_for("engineer@example.com")),
        json={
            "question": (
                "Calculate Reynolds number for velocity 2 m/s, diameter 0.05 m, "
                "density 998 kg/m3, and dynamic viscosity 0.001 Pa*s."
            )
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_source"] == "calculation"
    assert body["evidence_status"] == "sufficient"
    assert body["citations"] == []
    assert body["documents_used"] == []
    assert body["calculation"]["tool"] == "fluids"
    assert body["calculation"]["success"] is True
    assert body["calculation"]["outputs"][0]["value"] == pytest.approx(99800.0)
    assert "Calculated with fluids 1.3.1" in body["answer"]

    history = client.get(
        "/api/rag/history", headers=auth_header(token_for("engineer@example.com"))
    ).json()
    assert history[0]["retrieval_strategy"] == "fluids_tool"


def test_rag_api_reports_required_inputs_for_incomplete_calculation(
    client, make_user, token_for
):
    make_user("incomplete@example.com")
    response = client.post(
        "/api/rag/query",
        headers=auth_header(token_for("incomplete@example.com")),
        json={"question": "Calculate Reynolds number for velocity 2 m/s."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer_source"] == "calculation"
    assert body["evidence_status"] == "insufficient"
    assert body["calculation"]["success"] is False
    assert "diameter" in body["calculation"]["error"]


def test_rag_status_advertises_fluids_tool(client, make_user, token_for):
    make_user("status@example.com")
    response = client.get(
        "/api/rag/status", headers=auth_header(token_for("status@example.com"))
    )

    assert response.status_code == 200
    assert response.json()["fluids_tool_enabled"] is True
