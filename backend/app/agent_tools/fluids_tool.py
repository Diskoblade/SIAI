"""Bounded ``fluids`` calculations for the AI agent.

The LLM may select an operation and extract numeric arguments, but it cannot
choose an import, function name, or executable expression. Only the operations
declared here can reach the third-party library.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import fluids
from fluids.core import Cavitation, Froude, K_from_f, Mach, Reynolds, Weber, dP_from_K
from fluids.friction import friction_factor

from app.rag.reasoning import get_reasoner

TOOL_NAME = "fluids"
_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_CALCULATION_HINTS = re.compile(
    r"\b(?:calculate|compute|determine|evaluate|solve|estimate|work\s+out|find)\b",
    re.IGNORECASE,
)
_FLUID_HINTS = re.compile(
    r"\b(?:reynolds|friction\s+factor|pressure\s+(?:drop|loss)|head\s+loss|"
    r"froude|mach\s+number|weber|cavitation|pipe\s+flow|fluid\s+(?:flow|dynamics))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CalculationValue:
    key: str
    label: str
    value: float
    unit: str


@dataclass(frozen=True)
class FluidsCalculation:
    tool: str
    library_version: str
    operation: str
    title: str
    success: bool
    inputs: list[CalculationValue] = field(default_factory=list)
    outputs: list[CalculationValue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class Parameter:
    label: str
    unit: str
    minimum: float = 0.0
    allow_zero: bool = False
    maximum: float = 1.0e15


_PARAMETERS: dict[str, Parameter] = {
    "velocity": Parameter("Velocity", "m/s"),
    "diameter": Parameter("Diameter", "m"),
    "length": Parameter("Pipe length", "m"),
    "characteristic_length": Parameter("Characteristic length", "m"),
    "density": Parameter("Density", "kg/m^3"),
    "dynamic_viscosity": Parameter("Dynamic viscosity", "Pa*s"),
    "kinematic_viscosity": Parameter("Kinematic viscosity", "m^2/s"),
    "roughness": Parameter("Absolute roughness", "m", allow_zero=True),
    "relative_roughness": Parameter("Relative roughness", "", allow_zero=True),
    "reynolds_number": Parameter("Reynolds number", ""),
    "loss_coefficient": Parameter("Loss coefficient", "", allow_zero=True),
    "gravity": Parameter("Gravity", "m/s^2"),
    "speed_of_sound": Parameter("Speed of sound", "m/s"),
    "surface_tension": Parameter("Surface tension", "N/m"),
    "pressure": Parameter("Absolute pressure", "Pa", allow_zero=True),
    "vapor_pressure": Parameter("Vapor pressure", "Pa", allow_zero=True),
    "volumetric_flow_rate": Parameter("Volumetric flow rate", "m^3/s"),
}

_OPERATION_TITLES = {
    "reynolds_number": "Reynolds number",
    "friction_factor": "Darcy friction factor",
    "pipe_pressure_drop": "Straight-pipe pressure drop",
    "loss_pressure_drop": "Minor-loss pressure drop",
    "froude_number": "Froude number",
    "mach_number": "Mach number",
    "weber_number": "Weber number",
    "cavitation_number": "Cavitation number",
}

_ROUTER_PROMPT = """You route explicit fluid-dynamics calculation requests to a safe tool.
Use the tool only when the user asks to calculate, compute, solve, determine, or
estimate a numeric fluid-dynamics result. Convert supplied values to SI units.
Never invent a missing value. Return JSON with keys use_tool (bool), operation
(string), and arguments (object of numeric SI values).

Allowed operations and arguments:
- reynolds_number: velocity, diameter, and either density + dynamic_viscosity or kinematic_viscosity
- friction_factor: reynolds_number; optional relative_roughness
- pipe_pressure_drop: diameter, length, density, dynamic_viscosity, optional roughness, and either velocity or volumetric_flow_rate
- loss_pressure_drop: loss_coefficient, density, velocity
- froude_number: velocity, characteristic_length; optional gravity
- mach_number: velocity, speed_of_sound
- weber_number: velocity, characteristic_length, density, surface_tension
- cavitation_number: pressure, vapor_pressure, density, velocity

Do not return function names, Python code, units inside argument values, or any
argument not listed above."""


def is_fluids_calculation_request(question: str) -> bool:
    """Conservatively identify explicit numeric fluid calculation requests."""
    return bool(_CALCULATION_HINTS.search(question) and _FLUID_HINTS.search(question))


def run_fluids_tool(question: str) -> FluidsCalculation | None:
    """Route and execute one requested calculation, or return ``None``."""
    if not is_fluids_calculation_request(question):
        return None

    operation: str | None = None
    arguments: dict[str, Any] = {}
    reasoner = get_reasoner()
    if reasoner.available:
        decision = reasoner.complete_json(
            _ROUTER_PROMPT,
            f"User request: {question}",
            default={},
        )
        if isinstance(decision, dict) and decision.get("use_tool") is True:
            operation = decision.get("operation")
            candidate = decision.get("arguments")
            if isinstance(candidate, dict):
                arguments = candidate

    if operation not in _OPERATION_TITLES:
        operation, arguments = _parse_common_request(question)
    if operation not in _OPERATION_TITLES:
        return None
    return execute_fluids_calculation(operation, arguments)


def execute_fluids_calculation(
    operation: str, arguments: dict[str, Any]
) -> FluidsCalculation:
    """Validate arguments and execute one allow-listed library operation."""
    title = _OPERATION_TITLES.get(operation, "Fluid-dynamics calculation")
    if operation not in _OPERATION_TITLES:
        return _failure(operation, title, "This fluids operation is not supported.")

    try:
        args = _validated_arguments(arguments)
        if operation == "reynolds_number":
            return _reynolds(args)
        if operation == "friction_factor":
            return _friction_factor(args)
        if operation == "pipe_pressure_drop":
            return _pipe_pressure_drop(args)
        if operation == "loss_pressure_drop":
            return _loss_pressure_drop(args)
        if operation == "froude_number":
            return _dimensionless(
                operation,
                args,
                required=("velocity", "characteristic_length"),
                output=("froude_number", "Froude number"),
                calculate=lambda a: Froude(
                    V=a["velocity"],
                    L=a["characteristic_length"],
                    g=a.get("gravity", 9.80665),
                ),
                optional_defaults={"gravity": 9.80665},
            )
        if operation == "mach_number":
            return _dimensionless(
                operation,
                args,
                required=("velocity", "speed_of_sound"),
                output=("mach_number", "Mach number"),
                calculate=lambda a: Mach(V=a["velocity"], c=a["speed_of_sound"]),
            )
        if operation == "weber_number":
            return _dimensionless(
                operation,
                args,
                required=("velocity", "characteristic_length", "density", "surface_tension"),
                output=("weber_number", "Weber number"),
                calculate=lambda a: Weber(
                    V=a["velocity"],
                    L=a["characteristic_length"],
                    rho=a["density"],
                    sigma=a["surface_tension"],
                ),
            )
        return _dimensionless(
            operation,
            args,
            required=("pressure", "vapor_pressure", "density", "velocity"),
            output=("cavitation_number", "Cavitation number"),
            calculate=lambda a: Cavitation(
                P=a["pressure"],
                Psat=a["vapor_pressure"],
                rho=a["density"],
                V=a["velocity"],
            ),
        )
    except (ValueError, ArithmeticError, OverflowError) as exc:
        return _failure(operation, title, str(exc))


def format_fluids_answer(result: FluidsCalculation) -> str:
    """Create a deterministic answer so calculated values are not altered by an LLM."""
    if not result.success:
        return f"The {result.tool} tool could not complete the calculation: {result.error}"

    inputs = ", ".join(_format_value(item) for item in result.inputs)
    lines = [
        f"Calculated with {result.tool} {result.library_version}: {result.title}.",
        f"Inputs (SI): {inputs}.",
        "Results:",
    ]
    lines.extend(f"- {_format_value(item)}" for item in result.outputs)
    lines.extend(f"- {note}" for note in result.notes)
    return "\n".join(lines)


def _validated_arguments(arguments: dict[str, Any]) -> dict[str, float]:
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object of numeric SI values.")
    result: dict[str, float] = {}
    for key, raw in arguments.items():
        parameter = _PARAMETERS.get(key)
        if parameter is None:
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{parameter.label} must be numeric and expressed in SI units.")
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"{parameter.label} must be finite.")
        valid_minimum = value >= parameter.minimum if parameter.allow_zero else value > parameter.minimum
        if not valid_minimum or value > parameter.maximum:
            comparison = ">=" if parameter.allow_zero else ">"
            raise ValueError(
                f"{parameter.label} must be {comparison} {parameter.minimum:g} and no greater "
                f"than {parameter.maximum:g} {parameter.unit}."
            )
        result[key] = value
    return result


def _require(args: dict[str, float], *names: str) -> None:
    missing = [name for name in names if name not in args]
    if missing:
        labels = ", ".join(_PARAMETERS[name].label.lower() for name in missing)
        raise ValueError(f"Missing required inputs: {labels}.")


def _values(args: dict[str, float], names: tuple[str, ...]) -> list[CalculationValue]:
    return [
        CalculationValue(name, _PARAMETERS[name].label, args[name], _PARAMETERS[name].unit)
        for name in names
        if name in args
    ]


def _success(
    operation: str,
    inputs: list[CalculationValue],
    outputs: list[CalculationValue],
    notes: list[str] | None = None,
) -> FluidsCalculation:
    return FluidsCalculation(
        tool=TOOL_NAME,
        library_version=fluids.__version__,
        operation=operation,
        title=_OPERATION_TITLES[operation],
        success=True,
        inputs=inputs,
        outputs=outputs,
        notes=notes or [],
    )


def _failure(operation: str, title: str, error: str) -> FluidsCalculation:
    return FluidsCalculation(
        tool=TOOL_NAME,
        library_version=fluids.__version__,
        operation=operation,
        title=title,
        success=False,
        error=error,
    )


def _reynolds(args: dict[str, float]) -> FluidsCalculation:
    _require(args, "velocity", "diameter")
    kwargs: dict[str, float] = {"V": args["velocity"], "D": args["diameter"]}
    names = ["velocity", "diameter"]
    if "kinematic_viscosity" in args:
        kwargs["nu"] = args["kinematic_viscosity"]
        names.append("kinematic_viscosity")
    else:
        _require(args, "density", "dynamic_viscosity")
        kwargs.update(rho=args["density"], mu=args["dynamic_viscosity"])
        names.extend(("density", "dynamic_viscosity"))
    value = Reynolds(**kwargs)
    return _success(
        "reynolds_number",
        _values(args, tuple(names)),
        [CalculationValue("reynolds_number", "Reynolds number", value, "")],
        [_flow_regime(value)],
    )


def _friction_factor(args: dict[str, float]) -> FluidsCalculation:
    _require(args, "reynolds_number")
    relative_roughness = args.get("relative_roughness", 0.0)
    value = friction_factor(Re=args["reynolds_number"], eD=relative_roughness)
    effective = {**args, "relative_roughness": relative_roughness}
    return _success(
        "friction_factor",
        _values(effective, ("reynolds_number", "relative_roughness")),
        [CalculationValue("darcy_friction_factor", "Darcy friction factor", value, "")],
        [_flow_regime(args["reynolds_number"])],
    )


def _pipe_pressure_drop(args: dict[str, float]) -> FluidsCalculation:
    _require(args, "diameter", "length", "density", "dynamic_viscosity")
    velocity = args.get("velocity")
    if velocity is None:
        _require(args, "volumetric_flow_rate")
        velocity = 4.0 * args["volumetric_flow_rate"] / (math.pi * args["diameter"] ** 2)
    roughness = args.get("roughness", 0.0)
    re_value = Reynolds(
        V=velocity,
        D=args["diameter"],
        rho=args["density"],
        mu=args["dynamic_viscosity"],
    )
    relative_roughness = roughness / args["diameter"]
    fd = friction_factor(Re=re_value, eD=relative_roughness)
    loss_coefficient = K_from_f(fd=fd, L=args["length"], D=args["diameter"])
    pressure_drop = dP_from_K(K=loss_coefficient, rho=args["density"], V=velocity)
    effective = {**args, "velocity": velocity, "roughness": roughness}
    input_names = (
        "volumetric_flow_rate",
        "velocity",
        "diameter",
        "length",
        "density",
        "dynamic_viscosity",
        "roughness",
    )
    return _success(
        "pipe_pressure_drop",
        _values(effective, input_names),
        [
            CalculationValue("reynolds_number", "Reynolds number", re_value, ""),
            CalculationValue("relative_roughness", "Relative roughness", relative_roughness, ""),
            CalculationValue("darcy_friction_factor", "Darcy friction factor", fd, ""),
            CalculationValue("loss_coefficient", "Pipe loss coefficient", loss_coefficient, ""),
            CalculationValue("pressure_drop", "Pressure drop", pressure_drop, "Pa"),
        ],
        [_flow_regime(re_value), "Pressure drop uses the Darcy-Weisbach formulation."],
    )


def _loss_pressure_drop(args: dict[str, float]) -> FluidsCalculation:
    _require(args, "loss_coefficient", "density", "velocity")
    value = dP_from_K(
        K=args["loss_coefficient"], rho=args["density"], V=args["velocity"]
    )
    return _success(
        "loss_pressure_drop",
        _values(args, ("loss_coefficient", "density", "velocity")),
        [CalculationValue("pressure_drop", "Pressure drop", value, "Pa")],
    )


def _dimensionless(
    operation: str,
    args: dict[str, float],
    *,
    required: tuple[str, ...],
    output: tuple[str, str],
    calculate: Any,
    optional_defaults: dict[str, float] | None = None,
) -> FluidsCalculation:
    _require(args, *required)
    effective = {**(optional_defaults or {}), **args}
    names = required + tuple((optional_defaults or {}).keys())
    result = calculate(effective)
    return _success(
        operation,
        _values(effective, names),
        [CalculationValue(output[0], output[1], result, "")],
    )


def _flow_regime(reynolds: float) -> str:
    if reynolds < 2040.0:
        return "Flow regime: laminar (Re < 2040)."
    if reynolds < 4000.0:
        return "Flow regime: transitional; results are sensitive in this range."
    return "Flow regime: turbulent."


def _format_value(item: CalculationValue) -> str:
    value = f"{item.value:.8g}"
    return f"{item.label} = {value}{f' {item.unit}' if item.unit else ''}"


def _parse_common_request(question: str) -> tuple[str | None, dict[str, float]]:
    """Offline extraction for common, explicitly labelled SI requests."""
    q = question.lower()
    if "pressure drop" in q or "pressure loss" in q:
        operation = "loss_pressure_drop" if re.search(r"\b(?:loss\s+coefficient|k)\s*[=:]?\s*" + _NUMBER, q) else "pipe_pressure_drop"
    elif "friction factor" in q:
        operation = "friction_factor"
    elif "reynolds" in q:
        operation = "reynolds_number"
    elif "froude" in q:
        operation = "froude_number"
    elif "mach" in q:
        operation = "mach_number"
    elif "weber" in q:
        operation = "weber_number"
    elif "cavitation" in q:
        operation = "cavitation_number"
    else:
        return None, {}

    aliases: dict[str, tuple[str, ...]] = {
        "velocity": ("velocity", "speed"),
        "diameter": ("diameter", "pipe diameter"),
        "length": ("pipe length", "length"),
        "characteristic_length": ("characteristic length", "length"),
        "density": ("density",),
        "dynamic_viscosity": ("dynamic viscosity", "viscosity", "mu"),
        "kinematic_viscosity": ("kinematic viscosity", "nu"),
        "roughness": ("absolute roughness", "roughness"),
        "relative_roughness": ("relative roughness", "ed"),
        "reynolds_number": ("reynolds number", "re"),
        "loss_coefficient": ("loss coefficient", "k factor", "k"),
        "gravity": ("gravity",),
        "speed_of_sound": ("speed of sound", "sound speed"),
        "surface_tension": ("surface tension",),
        "pressure": ("absolute pressure", "pressure"),
        "vapor_pressure": ("vapor pressure", "vapour pressure"),
        "volumetric_flow_rate": ("volumetric flow rate", "flow rate"),
    }
    arguments: dict[str, float] = {}
    for key, labels in aliases.items():
        for label in labels:
            match = re.search(rf"\b{re.escape(label)}\b\s*(?:is|of|=|:)?\s*({_NUMBER})", q)
            if match:
                arguments[key] = float(match.group(1))
                break
    return operation, arguments
