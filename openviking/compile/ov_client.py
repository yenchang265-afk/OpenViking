"""In-process OpenViking access for Compile, with the HTTP client's method surface.

Every call runs as the task owner's RequestContext, so tenant identity and ACLs
match the original request. Storage errors are mapped like the HTTP routes map
them, so pipeline code keeps handling ``OpenVikingError`` codes such as NOT_FOUND.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from openviking.compile.embeddings import compile_embeddings
from openviking.pyagfs.exceptions import AGFSClientError, AGFSNotFoundError
from openviking.server.error_mapping import map_exception
from openviking.server.identity import RequestContext
from openviking_cli.exceptions import NotFoundError

# Source recorded on Skill packages that Compile creates or replaces.
_COMPILE_SKILL_SOURCE = {"type": "api", "source": "compile"}


@contextmanager
def _mapped_errors(uri: str) -> Iterator[None]:
    try:
        yield
    except AGFSNotFoundError as exc:
        raise NotFoundError(uri, "file") from exc
    except AGFSClientError as exc:
        mapped = map_exception(exc, resource=uri, resource_type="file")
        if mapped is not None:
            raise mapped from exc
        raise


class InProcessVikingClient:
    """Service-backed replacement for the bot's HTTP VikingClient."""

    def __init__(self, service: Any, ctx: RequestContext):
        self._service = service
        self._ctx = ctx

    async def stat(self, uri: str) -> dict[str, Any]:
        with _mapped_errors(uri):
            return await self._service.fs.stat(uri, ctx=self._ctx)

    async def read_raw(self, uri: str, offset: int = 0, limit: int = -1) -> str:
        with _mapped_errors(uri):
            return await self._service.fs.read(uri, ctx=self._ctx, offset=offset, limit=limit)

    async def download_bytes(self, uri: str) -> bytes:
        with _mapped_errors(uri):
            return await self._service.fs.read_file_bytes(uri, ctx=self._ctx)

    async def list_resources(
        self, path: str, node_limit: int = 1000, *, offset: int = 0
    ) -> list[dict[str, Any]]:
        with _mapped_errors(path):
            page = await self._service.fs.ls(
                path, ctx=self._ctx, node_limit=node_limit, offset=offset
            )
        return page.entries

    async def mkdir(self, uri: str) -> None:
        with _mapped_errors(uri):
            await self._service.fs.mkdir(uri, ctx=self._ctx)

    async def glob(self, pattern: str, uri: str) -> dict[str, Any]:
        with _mapped_errors(uri):
            return await self._service.fs.glob(pattern, ctx=self._ctx, uri=uri)

    async def find(self, query: str, *, target_uri: str, limit: int = 10) -> Any:
        return await self._service.search.find(
            query=query, ctx=self._ctx, target_uri=target_uri, limit=limit
        )

    async def compile_embeddings(
        self, texts: list[str], *, target_uri: str, expected_model: str | None = None
    ) -> dict[str, Any]:
        return await compile_embeddings(
            self._service,
            self._ctx,
            texts,
            target_uri=target_uri,
            expected_model=expected_model,
        )

    async def batch_write(
        self,
        *,
        root_uri: str,
        operations: list[dict[str, Any]],
        wait: bool = True,
        skip_conflicts: bool = False,
    ) -> dict[str, Any]:
        # Validate like the HTTP route so rendered operations keep the same contract.
        from openviking.server.routers.content import BatchWriteOperation

        validated = [
            BatchWriteOperation.model_validate(operation).model_dump(exclude_none=True)
            for operation in operations
        ]
        with _mapped_errors(root_uri):
            return await self._service.fs.batch_write(
                root_uri=root_uri,
                operations=validated,
                ctx=self._ctx,
                wait=wait,
                skip_conflicts=skip_conflicts,
            )

    async def get_skill(self, skill_name: str, *, target_uri: str) -> dict[str, Any]:
        from openviking.server.routers.skills import _read_skill_detail, _require_skill

        root_uri = await _require_skill(self._service, self._ctx, skill_name, target_uri)
        return await _read_skill_detail(
            self._service,
            self._ctx,
            skill_name=skill_name,
            root_uri=root_uri,
            include_content=True,
            include_files=True,
            include_integrity=False,
            include_source=False,
            level=None,
        )

    async def add_skill(self, path: str, *, target_uri: str, wait: bool = True) -> dict[str, Any]:
        # The package directory is a server-owned temporary directory.
        return await self._service.resources.add_skill(
            data=Path(path),
            ctx=self._ctx,
            wait=wait,
            allow_local_path_resolution=True,
            target_uri=target_uri,
            source_metadata={**_COMPILE_SKILL_SOURCE, "operation": "add"},
        )

    async def update_skill(
        self, skill_name: str, path: str, *, target_uri: str, wait: bool = True
    ) -> dict[str, Any]:
        from openviking.server.routers.skills import _require_skill, apply_skill_update

        root_uri = await _require_skill(self._service, self._ctx, skill_name, target_uri)
        return await apply_skill_update(
            self._service,
            self._ctx,
            skill_name=skill_name,
            root_uri=root_uri,
            data=Path(path),
            allow_local_path_resolution=True,
            source_metadata={**_COMPILE_SKILL_SOURCE, "operation": "update"},
            wait=wait,
        )
