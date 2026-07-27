"""Pure closed-vocabulary contract for advisory Simulation Lab directives."""


class DirectiveValidationError(ValueError):
    """Raised when model output is not an exact directive-code selection."""


_DIRECTIVE_TEMPLATES = {
    "P6_SCHEDULE_REVIEW": {
        "system": "P6",
        "action": "Review schedule recovery options",
        "description": (
            "A project scheduler should assess affected activities, dependencies, and approvals "
            "before requesting any schedule change."
        ),
        "status": "For Review",
    },
    "CREW_PLAN_REVIEW": {
        "system": "Operational Review",
        "action": "Review the proposed crew plan",
        "description": (
            "The project team should assess crew availability, site constraints, safety requirements, "
            "and approvals before changing the field plan."
        ),
        "status": "For Review",
    },
    "PROCUREMENT_REVIEW": {
        "system": "SAP",
        "action": "Review procurement recovery options",
        "description": (
            "A procurement reviewer should assess material availability, supplier commitments, "
            "commercial constraints, and approvals before requesting any procurement change."
        ),
        "status": "For Review",
    },
    "TC_RECOVERY_REVIEW": {
        "system": "Operational Review",
        "action": "Review transmission recovery options",
        "description": (
            "The transmission team should assess at-risk work, dependencies, contractor capacity, "
            "and required approvals before changing the recovery plan."
        ),
        "status": "For Review",
    },
    "PMAG_ACTION_REVIEW": {
        "system": "PMAG",
        "action": "Review the proposed PMAG action",
        "description": (
            "An authorized reviewer should assess the proposed project action and required approvals "
            "before requesting any PMAG change."
        ),
        "status": "For Review",
    },
}

SIMULATION_DIRECTIVE_CODES = tuple(_DIRECTIVE_TEMPLATES)
_MAX_DIRECTIVES = len(SIMULATION_DIRECTIVE_CODES)


def build_simulation_directives(payload: object) -> dict[str, list[dict[str, str]]]:
    """Map an exact model-selected code list to backend-owned directive text."""

    if not isinstance(payload, dict) or set(payload) != {"directive_codes"}:
        raise DirectiveValidationError("Directive response must contain only directive_codes.")

    codes = payload["directive_codes"]
    if not isinstance(codes, list) or not 1 <= len(codes) <= _MAX_DIRECTIVES:
        raise DirectiveValidationError("Directive code list is outside allowed bounds.")
    if any(not isinstance(code, str) for code in codes):
        raise DirectiveValidationError("Every directive code must be a string.")
    if len(set(codes)) != len(codes):
        raise DirectiveValidationError("Directive codes must be unique.")
    if any(code not in _DIRECTIVE_TEMPLATES for code in codes):
        raise DirectiveValidationError("Directive code is not supported.")

    return {
        "tasks": [dict(_DIRECTIVE_TEMPLATES[code]) for code in codes]
    }
