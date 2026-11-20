"""Shared tools for private file-tool workers.

Upstream runs workers through VikingBot's AgentLoop (``agent_runner`` in upstream's
pipeline_agent.py). In-server Compile runs them in ``agent_loop.py``; this module keeps
the worker tool that both implementations share.
"""

from __future__ import annotations

import json

from openviking.compile import file_ops
from openviking.compile.renderer import validate_relative_file_path
from openviking.compile.tool import Tool


class TargetReader(Tool):
    """Read a known target path and remember its revision before allowing replacement."""

    name = "read_target_file"
    description = "Read an existing file under the output destination before updating it."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to request.to."}
        },
        "required": ["path"],
    }

    def __init__(self, runtime):
        self.runtime = runtime

    async def execute(self, tool_context=None, path=""):
        """Return existing UTF-8 Markdown or an explicit missing-file result; errors propagate."""
        path = validate_relative_file_path(path)
        content = await file_ops.load_old(self.runtime, path)
        if isinstance(content, bytes):
            raise ValueError("Target is not UTF-8 text")
        return json.dumps({"path": path, "content": content}, ensure_ascii=False)
