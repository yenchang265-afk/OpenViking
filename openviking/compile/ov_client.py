"""In-process OpenViking access for Compile, with the HTTP client's method surface.

Every call runs as the task owner's RequestContext, so tenant identity and ACLs
match the original request. Storage errors are mapped like the HTTP routes map
them, so pipeline code keeps handling ``OpenVikingError`` codes such as NOT_FOUND.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from openviking.compile.embeddings import compile_embeddings
from openviking.pyagfs.exceptions import AGFSClientError, AGFSNotFoundError
from openviking.server.error_mapping import map_exception
from openviking.server.identity import RequestContext
from openviking_cli.exceptions import InvalidArgumentError, NotFoundError, OpenVikingError

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
    """Service-backed replacement for the bot's HTTP VikingClient.

    With a ``skill_snapshot`` (``{"uri", "snapshot_id"}``), reads inside that Skill
    package come from the pinned commit, so an incremental run uses the Skill it
    was planned with; everything else stays live.
    """

    def __init__(
        self,
        service: Any,
        ctx: RequestContext,
        *,
        skill_snapshot: Mapping[str, Any] | None = None,
        edit_source: str | None = None,
    ):
        self._service = service
        self._ctx = ctx
        snapshot_id = (skill_snapshot or {}).get("snapshot_id")
        if snapshot_id and not re.fullmatch(r"[0-9a-fA-F]{40}", str(snapshot_id)):
            raise ValueError("Skill snapshot_id must be a commit ID")
        self._skill_snapshot = dict(skill_snapshot) if snapshot_id else None
        # Recorded on published files; "compile" defers indexing to task finalization.
        self._edit_source = edit_source

    def is_pinned_skill_uri(self, uri: str) -> bool:
        """True for URIs inside the pinned Skill package, whose reads use the snapshot."""
        return self._snapshot_ref(uri) is not None

    def _snapshot_ref(self, uri: str) -> str | None:
        snapshot = self._skill_snapshot
        if snapshot and (uri == snapshot["uri"] or uri.startswith(snapshot["uri"] + "/")):
            return snapshot["snapshot_id"]
        return None

    async def stat(self, uri: str) -> dict[str, Any]:
        if self._snapshot_ref(uri):
            try:
                data = await self.download_bytes(uri)
            except OpenVikingError as exc:
                # Git reports existing trees through its invalid-operation response.
                if "path is a directory, not a file:" not in str(exc):
                    raise
                return {"uri": uri, "isDir": True, "size": 0}
            return {"uri": uri, "isDir": False, "size": len(data)}
        with _mapped_errors(uri):
            return await self._service.fs.stat(uri, ctx=self._ctx)

    async def read_raw(self, uri: str, offset: int = 0, limit: int = -1) -> str:
        if self._snapshot_ref(uri):
            if offset < 0 or limit < -1:
                raise ValueError("Invalid snapshot line range")
            lines = (await self.download_bytes(uri)).decode("utf-8").splitlines(keepends=True)
            return "".join(lines[offset:] if limit == -1 else lines[offset : offset + limit])
        with _mapped_errors(uri):
            return await self._service.fs.read(uri, ctx=self._ctx, offset=offset, limit=limit)

    async def download_bytes(self, uri: str) -> bytes:
        snapshot_id = self._snapshot_ref(uri)
        with _mapped_errors(uri):
            if snapshot_id:
                try:
                    blob = await self._service.fs.show_blob_raw(
                        snapshot_id, path=uri, ctx=self._ctx
                    )
                except ValueError as exc:
                    raise InvalidArgumentError(str(exc)) from exc
                return blob["bytes"]
            return await self._service.fs.read_file_bytes(uri, ctx=self._ctx)

    async def diff_paths(
        self,
        dirs: list[str],
        *,
        head: str,
        base: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return one directory-change page; a null base compares an empty tree."""
        with _mapped_errors(dirs[0] if dirs else ""):
            return await self._service.fs.diff_paths(
                list(dirs), from_ref=base, to_ref=head, offset=offset, limit=limit, ctx=self._ctx
            )

    async def list_resources(
        self, path: str, node_limit: int = 1000, *, offset: int = 0
    ) -> list[dict[str, Any]]:
        with _mapped_errors(path):
            page = await self._service.fs.ls(
                path, ctx=self._ctx, node_limit=node_limit, offset=offset
            )
        return page.entries

    async def mkdir(self, uri: str, *, description: str | None = None) -> None:
        with _mapped_errors(uri):
            await self._service.fs.mkdir(uri, ctx=self._ctx, description=description)

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
        compile_edit = self._edit_source == "compile"
        with _mapped_errors(root_uri):
            return await self._service.fs.batch_write(
                root_uri=root_uri,
                operations=validated,
                ctx=self._ctx,
                wait=wait,
                skip_conflicts=skip_conflicts,
                # Compile output is indexed by the write's own refresh task; the
                # lifecycle only finalizes the target directory when the run finishes.
                **({"edit_source": "compile"} if compile_edit else {}),
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
