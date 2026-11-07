"""Canonical storage selector with a backwards-compatible provider spelling."""

from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator


def backend_name(data: dict, path: str = "storage") -> Any:
    if "backend" in data and "provider" in data and data["backend"] != data["provider"]:
        raise ValueError(f"{path}.backend and legacy provider must not conflict")
    return data.get("backend", data.get("provider"))


class BackendSelectorConfig(BaseModel):
    """Keep the Python provider attribute while serializing canonical ov.conf keys."""

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def validate_selector_alias(cls, data):
        if isinstance(data, dict):
            backend_name(data, cls.__name__)
            if "backend" in data and "provider" in data:
                data = {key: value for key, value in data.items() if key != "provider"}
        return data

    @model_serializer(mode="wrap")
    def serialize_backend(self, handler):
        result = handler(self)
        if "provider" in result:
            result["backend"] = result.pop("provider")
        return result
