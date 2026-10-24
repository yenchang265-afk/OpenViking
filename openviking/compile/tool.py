"""Minimal model-callable tool contract for Compile readers and agent tools."""

from __future__ import annotations

from typing import Any


class Tool:
    """A function tool exposed to the model; subclasses set the schema and implement execute.

    Compile calls ``execute(**arguments)`` directly with the model's parsed arguments.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    async def execute(self, **kwargs: Any) -> str:
        raise NotImplementedError

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
