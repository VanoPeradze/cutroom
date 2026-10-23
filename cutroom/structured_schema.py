"""Closed object alternatives for the local structured-output grammar.

Do not rely on a converter intersecting properties/required beside anyOf.
This builder only expands CUTROOM's property restrictions; it is not a general
JSON Schema normalizer. Response validation remains the caller's responsibility.
"""
from __future__ import annotations

import copy


def _restrict(base, restriction):
    allowed = {"type", "const", "enum", "items", "uniqueItems", "minItems", "maxItems",
               "minLength", "maxLength", "minimum", "maximum"}
    if set(restriction) - allowed:
        raise ValueError("Unsupported property restriction in object alternative")
    result = copy.deepcopy(base)
    for key, value in restriction.items():
        if key not in result:
            result[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = _restrict(result[key], value)
        elif key == "enum":
            if any(item not in result[key] for item in value):
                raise ValueError("An object alternative must not broaden an enum")
            result[key] = copy.deepcopy(value)
        elif key in {"minItems", "minLength", "minimum"}:
            result[key] = max(result[key], value)
        elif key in {"maxItems", "maxLength", "maximum"}:
            result[key] = min(result[key], value)
        elif result[key] != value:
            raise ValueError(f"Unsupported object alternative intersection: {key}")
    if "const" in result and "enum" in result:
        if result["const"] not in result["enum"]:
            raise ValueError("An object alternative constant contradicts its enum")
        del result["enum"]  # The checked constant is the complete intersection.
    return result


def complete_object_union(schema):
    """Move common closed-object constraints into every anyOf alternative.

    Only properties-only restrictions are accepted. Each emitted branch owns all
    properties, required fields and additionalProperties=false. Neither the input
    nor its nested evidence schemas are mutated.
    """
    if (set(schema) != {"type", "properties", "required", "additionalProperties", "anyOf"}
            or schema["type"] != "object" or schema["additionalProperties"] is not False
            or not schema["anyOf"]):
        raise ValueError("Expected a closed object with property alternatives")
    common = {key: copy.deepcopy(value) for key, value in schema.items() if key != "anyOf"}
    branches = []
    for variant in schema["anyOf"]:
        if set(variant) != {"properties"} or set(variant["properties"]) - set(common["properties"]):
            raise ValueError("Unsupported object alternative shape")
        branch = copy.deepcopy(common)
        for name, restriction in variant["properties"].items():
            branch["properties"][name] = _restrict(branch["properties"][name], restriction)
        branches.append(branch)
    return {"anyOf": branches}
