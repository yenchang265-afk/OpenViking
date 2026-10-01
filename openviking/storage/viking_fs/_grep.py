# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Grep and search-backend mixin for VikingFS."""

import asyncio
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Set

from openviking.core.namespace import is_session_uri
from openviking.pyagfs.exceptions import AGFSNotSupportedError
from openviking.server.identity import RequestContext
from openviking.storage.expr import And, PathScope, RawDSL
from openviking.storage.viking_fs._base import logger
from openviking_cli.exceptions import PermissionDeniedError

_GREP_LS_PAGE_SIZE = 1000


def _pkg():
    return sys.modules[__package__]


class _GrepMixin:
    """Grep and search-backend methods."""

    async def grep(
        self,
        uri: str,
        pattern: str,
        exclude_uri: Optional[str] = None,
        case_insensitive: bool = False,
        node_limit: Optional[int] = None,
        level_limit: int = 10,
        ctx: Optional[RequestContext] = None,
        content_transform: Optional[Callable[[str, str], str]] = None,
        allowed_uris: Optional[Set[str]] = None,
        tag_filter: Optional[Dict[str, Any]] = None,
        before_context: int = 0,
        after_context: int = 0,
    ) -> Dict:
        """Content search by pattern or keywords.

        Optimized implementation that uses agfs native grep when possible.
        The ragfs layer greps transparently over encrypted and plaintext files
        (it decrypts via account_id when an encryption layer is configured).
        Falls back to VikingFS layer implementation if native grep is unavailable.

        Args:
            uri: Viking URI
            pattern: Regular expression pattern to search for
            exclude_uri: Optional URI prefix to exclude from search
            case_insensitive: Whether to perform case-insensitive matching
            node_limit: Maximum number of results to return
            level_limit: Maximum depth level to traverse (default: 10)
            ctx: Request context
            content_transform: Optional projection applied before regex matching.
            before_context: Number of lines to include before each match.
            after_context: Number of lines to include after each match.

        Returns:
            Dict with matches, count, match_count, files_scanned
        """
        await self._ensure_access(uri, ctx)
        # Skip vector_store.count() — the count field is not needed for grep.
        await self.stat(uri, ctx=ctx, skip_count=True)

        tags_by_uri: Dict[str, List[str]] = {}
        if tag_filter is not None:
            vector_store = self._get_vector_store()
            if vector_store is None:
                return {"matches": [], "count": 0, "match_count": 0, "files_scanned": 0}
            records = await vector_store.filter(
                filter=And(
                    [
                        PathScope("uri", uri, depth=level_limit),
                        RawDSL(tag_filter),
                    ]
                ),
                limit=100000,
                output_fields=["uri", "search_tags"],
                ctx=ctx,
            )
            allowed_uris = {str(record["uri"]) for record in records if record.get("uri")}
            if not allowed_uris:
                return {"matches": [], "count": 0, "match_count": 0, "files_scanned": 0}
            tags_by_uri = {
                str(record["uri"]): list(record.get("search_tags") or [])
                for record in records
                if record.get("uri")
            }

        result = await self._grep_fs(
            uri=uri,
            pattern=pattern,
            exclude_uri=exclude_uri,
            case_insensitive=case_insensitive,
            node_limit=node_limit,
            level_limit=level_limit,
            ctx=ctx,
            content_transform=content_transform,
            allowed_uris=allowed_uris,
            before_context=before_context,
            after_context=after_context,
        )
        return self._attach_grep_tags(result, tags_by_uri)

    async def _grep_fs(
        self,
        uri,
        pattern,
        exclude_uri,
        case_insensitive,
        node_limit,
        level_limit,
        ctx,
        content_transform=None,
        allowed_uris=None,
        before_context=0,
        after_context=0,
    ):
        """Filesystem grep path: prefer native agfs grep and fall back if unavailable."""
        native_safe = (
            content_transform is None
            and allowed_uris is None
            and await self._session_native_grep_safe(uri, ctx)
        )
        if native_safe:
            try:
                # Session grep historically used the Python fallback, where
                # level_limit counts directory expansions and therefore
                # includes files one path segment deeper than native grep.
                # Preserve that public behavior when selecting the fast path.
                native_level_limit = (
                    level_limit + 1
                    if is_session_uri(uri) and level_limit is not None
                    else level_limit
                )
                return await self._grep_with_agfs(
                    uri=uri,
                    pattern=pattern,
                    exclude_uri=exclude_uri,
                    case_insensitive=case_insensitive,
                    node_limit=node_limit,
                    level_limit=native_level_limit,
                    ctx=ctx,
                    before_context=before_context,
                    after_context=after_context,
                )
            except (AttributeError, AGFSNotSupportedError, NotImplementedError) as e:
                logger.debug(f"agfs grep unavailable, falling back to VikingFS implementation: {e}")

        return await self._grep_encrypted(
            uri=uri,
            pattern=pattern,
            exclude_uri=exclude_uri,
            case_insensitive=case_insensitive,
            node_limit=node_limit,
            level_limit=level_limit,
            ctx=ctx,
            content_transform=content_transform,
            allowed_uris=allowed_uris,
            before_context=before_context,
            after_context=after_context,
        )

    async def _session_native_grep_safe(self, uri: str, ctx: Optional[RequestContext]) -> bool:
        """Return whether native grep sees every visible path for ``uri``.

        Canonical session reads merge the current user namespace with two
        historical storage layouts. Native AGFS grep accepts one physical
        root, so it is complete only when no visible legacy candidate exists.
        """
        legacy_uri = self._legacy_session_alias(uri)
        if legacy_uri is None:
            return True

        real_ctx = self._ctx_or_default(ctx)
        if self._is_session_root_uri(uri):
            primary_path = self._uri_to_path(uri, ctx=ctx)
            if not await self._agfs_path_exists(primary_path):
                return False
            legacy_path = self._legacy_session_path(legacy_uri, ctx=ctx)
            owner_user_id = self._safe_uri_parts(uri)[1]
            legacy_items = await self._legacy_session_root_items(
                legacy_path, real_ctx, uri.rstrip("/"), owner_user_id
            )
            return not legacy_items

        primary_path = self._uri_to_path(uri, ctx=ctx)
        for path in self._read_paths(uri, ctx=ctx)[1:]:
            if not await self._agfs_path_exists(path):
                continue
            if await self._read_path_visible(uri, path, primary_path, real_ctx):
                return False
        return True

    @staticmethod
    def _attach_grep_tags(result: Dict, tags_by_uri: Dict[str, List[str]]) -> Dict:
        if not tags_by_uri:
            return result
        result = dict(result)
        result["matches"] = [
            {**match, "tags": tags_by_uri.get(str(match.get("uri") or ""), [])}
            for match in result.get("matches", [])
        ]
        return result

    async def _grep_with_agfs(
        self,
        uri: str,
        pattern: str,
        exclude_uri: Optional[str] = None,
        case_insensitive: bool = False,
        node_limit: Optional[int] = None,
        level_limit: int = 10,
        ctx: Optional[RequestContext] = None,
        before_context: int = 0,
        after_context: int = 0,
    ) -> Dict:
        """Grep using agfs native implementation.

        This is the optimized path for non-encrypted files.
        Uses agfs.grep() which performs matching on the server side.

        Prefer pushing filters down to agfs backend:
        - exclude_uri -> exclude_path
        - level_limit -> level_limit

        Args:
            uri: Viking URI
            pattern: Regular expression pattern to search for
            exclude_uri: Optional URI prefix to exclude from search
            case_insensitive: Whether to perform case-insensitive matching
            node_limit: Maximum number of results to return
            level_limit: Maximum depth level to traverse
            ctx: Request context
            before_context: Number of lines to include before each match
            after_context: Number of lines to include after each match

        Returns:
            Dict with matches, count, match_count, files_scanned
        """
        path = self._uri_to_path(uri, ctx=ctx)

        excluded_path = None
        if exclude_uri:
            normalized_excluded_uri = exclude_uri.rstrip("/")
            await self._ensure_access(normalized_excluded_uri, ctx)
            excluded_path = self._uri_to_path(normalized_excluded_uri, ctx=ctx)

        try:
            result = await self._async_agfs.grep(
                path=path,
                pattern=pattern,
                recursive=True,
                case_insensitive=case_insensitive,
                stream=False,
                node_limit=node_limit,
                exclude_path=excluded_path,
                level_limit=level_limit,
                before_context=before_context,
                after_context=after_context,
            )
        except (AttributeError, AGFSNotSupportedError, NotImplementedError):
            # Capability missing: let the outer caller fall back to the VikingFS implementation.
            logger.warning("agfs grep unavailable, falling back to VikingFS implementation")
            raise

        matches = result.get("matches", [])
        results = []
        files_scanned_set = set()
        real_ctx = self._ctx_or_default(ctx)

        # Resolve every matched file to a Viking URI first, then run one
        # ACL-aware batch authorization. ``_is_accessible`` is ACL-blind for
        # ``viking://resources`` and would leak content protected by restricted
        # inheritance, so matched URIs must go through ``_can_access_many`` the
        # same way filesystem reads and vector retrieval do.
        match_uris: List[str] = []
        for match in matches:
            match_file = match.get("file", "")
            if not match_file:
                continue
            agfs_file_path = self._resolve_grep_match_agfs_path(path, match_file)
            match_uris.append(self._path_to_uri(agfs_file_path, ctx=ctx))

        access = await self._can_access_many(match_uris, real_ctx)

        for match in matches:
            match_file = match.get("file", "")
            if not match_file:
                continue

            agfs_file_path = self._resolve_grep_match_agfs_path(path, match_file)

            file_uri = self._path_to_uri(agfs_file_path, ctx=ctx)
            if not access.get(file_uri, False):
                continue

            files_scanned_set.add(file_uri)

            mapped_match = {
                "line": match.get("line", match.get("line_number", 0)),
                "uri": file_uri,
                "content": match.get("content", ""),
            }
            if before_context > 0:
                mapped_match["before_context"] = match.get("before_context", [])
            if after_context > 0:
                mapped_match["after_context"] = match.get("after_context", [])
            results.append(mapped_match)

            if node_limit and len(results) >= node_limit:
                break

        # Prefer backend-provided scanned file count if available; otherwise fall back to
        # counting files that produced at least one match (best-effort).
        backend_files_scanned = result.get("files_scanned")
        if isinstance(backend_files_scanned, int) and backend_files_scanned >= 0:
            files_scanned = (
                len(files_scanned_set) if real_ctx.actor_peer_id else backend_files_scanned
            )
        else:
            files_scanned = len(files_scanned_set)

        return {
            "matches": results,
            "count": len(results),
            "match_count": len(results),
            "files_scanned": files_scanned,
        }

    async def _grep_encrypted(
        self,
        uri: str,
        pattern: str,
        exclude_uri: Optional[str] = None,
        case_insensitive: bool = False,
        node_limit: Optional[int] = None,
        level_limit: int = 10,
        ctx: Optional[RequestContext] = None,
        content_transform: Optional[Callable[[str, str], str]] = None,
        allowed_uris: Optional[Set[str]] = None,
        before_context: int = 0,
        after_context: int = 0,
    ) -> Dict:
        """Grep implementation for encrypted files.

        This implementation decrypts files at VikingFS layer before matching.
        Used when encryption is enabled or when agfs.grep is not available.

        Args:
            uri: Viking URI
            pattern: Regular expression pattern to search for
            exclude_uri: Optional URI prefix to exclude from search
            case_insensitive: Whether to perform case-insensitive matching
            node_limit: Maximum number of results to return
            level_limit: Maximum depth level to traverse (default: 10)
            ctx: Request context

        Returns:
            Dict with matches, count, match_count, files_scanned
        """
        flags = re.IGNORECASE if case_insensitive else 0
        compiled_pattern = re.compile(pattern, flags)
        excluded_prefix = None
        if exclude_uri:
            excluded_prefix = exclude_uri.rstrip("/")
            await self._ensure_access(excluded_prefix, ctx)
        file_uris = await self._collect_grep_files(
            uri,
            excluded_prefix=excluded_prefix,
            level_limit=level_limit,
            ctx=ctx,
            allowed_uris=allowed_uris,
        )
        results, files_scanned = await self._grep_files_parallel(
            file_uris,
            compiled_pattern=compiled_pattern,
            node_limit=node_limit,
            ctx=ctx,
            content_transform=content_transform,
            before_context=before_context,
            after_context=after_context,
        )

        return {
            "matches": results,
            "count": len(results),
            "match_count": len(results),
            "files_scanned": files_scanned,
        }

    async def _collect_grep_files(
        self,
        uri: str,
        excluded_prefix: Optional[str],
        level_limit: int,
        ctx: Optional[RequestContext] = None,
        allowed_uris: Optional[Set[str]] = None,
    ) -> List[str]:
        file_uris: List[str] = []

        async def search_recursive(current_uri: str, current_depth: int) -> None:
            if current_depth > level_limit:
                return

            normalized_current_uri = current_uri
            if excluded_prefix and (
                normalized_current_uri == excluded_prefix
                or normalized_current_uri.startswith(excluded_prefix + "/")
            ):
                logger.debug(f"Skipping excluded uri during grep: {normalized_current_uri}")
                return

            offset = 0
            while True:
                try:
                    entries = await self.ls(
                        normalized_current_uri,
                        node_limit=_GREP_LS_PAGE_SIZE,
                        offset=offset,
                        ctx=ctx,
                    )
                except PermissionDeniedError:
                    # A denial on the first page means this child subtree is
                    # no longer visible and can be skipped. Once traversal has
                    # consumed a page, swallowing the error would misreport a
                    # partial result as complete.
                    if current_depth == 0 or offset > 0:
                        raise
                    logger.debug(
                        f"Skipping inaccessible directory during grep: {normalized_current_uri}"
                    )
                    return

                for entry in entries:
                    entry_uri = f"{normalized_current_uri.rstrip('/')}/{entry['name']}"
                    if excluded_prefix and (
                        entry_uri == excluded_prefix or entry_uri.startswith(excluded_prefix + "/")
                    ):
                        logger.debug(f"Skipping excluded uri during grep: {entry_uri}")
                        continue
                    if entry.get("access") == "denied":
                        logger.debug(f"Skipping inaccessible uri during grep: {entry_uri}")
                        continue

                    if entry.get("isDir"):
                        await search_recursive(entry_uri, current_depth + 1)
                    elif allowed_uris is None or entry_uri in allowed_uris:
                        file_uris.append(entry_uri)

                if len(entries) < _GREP_LS_PAGE_SIZE:
                    break
                offset += len(entries)

        normalized_uri = uri
        if excluded_prefix and (
            normalized_uri == excluded_prefix or normalized_uri.startswith(excluded_prefix + "/")
        ):
            logger.debug(f"Skipping excluded uri during grep: {normalized_uri}")
            return file_uris
        root_stat = await self.stat(normalized_uri, ctx=ctx, skip_count=True)
        if not root_stat.get("isDir", False):
            if allowed_uris is None or normalized_uri in allowed_uris:
                file_uris.append(normalized_uri)
            return file_uris

        await search_recursive(uri, 0)
        return file_uris

    async def _grep_files_parallel(
        self,
        file_uris: List[str],
        compiled_pattern: re.Pattern,
        node_limit: Optional[int],
        ctx: Optional[RequestContext] = None,
        content_transform: Optional[Callable[[str, str], str]] = None,
        before_context: int = 0,
        after_context: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        results: List[Dict[str, Any]] = []
        files_scanned = 0
        concurrency = _pkg()._DEFAULT_GREP_FILE_CONCURRENCY
        for start in range(0, len(file_uris), concurrency):
            batch_uris = file_uris[start : start + concurrency]
            remaining_limit = node_limit - len(results) if node_limit else None
            batch_jobs = [
                self._grep_single_file(
                    entry_uri,
                    compiled_pattern,
                    ctx,
                    node_limit=remaining_limit,
                    content_transform=content_transform,
                    before_context=before_context,
                    after_context=after_context,
                )
                for entry_uri in batch_uris
            ]
            batch_results = await asyncio.gather(*batch_jobs)
            for matches, scanned_count in batch_results:
                files_scanned += scanned_count
                for match in matches:
                    results.append(match)
                    if node_limit and len(results) >= node_limit:
                        return results, files_scanned

        return results, files_scanned

    async def _grep_single_file(
        self,
        entry_uri: str,
        compiled_pattern: re.Pattern,
        ctx: Optional[RequestContext] = None,
        node_limit: Optional[int] = None,
        content_transform: Optional[Callable[[str, str], str]] = None,
        before_context: int = 0,
        after_context: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        try:
            content = await self.read(entry_uri, ctx=ctx)
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            if content_transform is not None:
                content = content_transform(content, entry_uri)

            matches: List[Dict[str, Any]] = []
            lines = content.split("\n")
            for line_index, line in enumerate(lines):
                if compiled_pattern.search(line):
                    matches.append(
                        self._build_grep_match(
                            entry_uri,
                            lines,
                            line_index,
                            before_context,
                            after_context,
                        )
                    )
                    if node_limit and len(matches) >= node_limit:
                        break
            return matches, 1
        except Exception as e:
            logger.debug(f"Failed to grep {entry_uri}: {e}")
            return [], 1

    @staticmethod
    def _build_grep_match(
        uri: str,
        lines: List[str],
        line_index: int,
        before_context: int,
        after_context: int,
    ) -> Dict[str, Any]:
        match = {
            "line": line_index + 1,
            "uri": uri,
            "content": lines[line_index],
        }
        if before_context > 0:
            start = max(0, line_index - before_context)
            match["before_context"] = [
                {"line": index + 1, "content": lines[index]}
                for index in range(start, line_index)
            ]
        if after_context > 0:
            end = min(len(lines), line_index + after_context + 1)
            match["after_context"] = [
                {"line": index + 1, "content": lines[index]}
                for index in range(line_index + 1, end)
            ]
        return match

    def _resolve_grep_match_agfs_path(self, base_path: str, match_file: str) -> str:
        """Resolve a grep match path (relative to query root) into a full AGFS path."""
        if match_file == ".":
            return base_path
        return f"{base_path.rstrip('/')}/{match_file.lstrip('/')}"
