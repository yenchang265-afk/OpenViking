"""Cluster-wide Studio presentation switches; underlying APIs remain available."""

from pydantic import BaseModel, ConfigDict

from .runtime_field import RuntimeField


class StudioFeaturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filesystem: bool = RuntimeField(default=True, strict=True)
    directory: bool = RuntimeField(default=True, strict=True)
    memories: bool = RuntimeField(default=True, strict=True)
    retrieval: bool = RuntimeField(default=True, strict=True)
    skills: bool = RuntimeField(default=True, strict=True)
    sessions: bool = RuntimeField(default=True, strict=True)
    tasks: bool = RuntimeField(default=True, strict=True)
    home: bool = RuntimeField(default=True, strict=True)
    vikingbot: bool = RuntimeField(default=True, strict=True)
    compile: bool = RuntimeField(default=True, strict=True)
    agentExperience: bool = RuntimeField(default=True, strict=True)
    requestLogs: bool = RuntimeField(default=True, strict=True)
    watches: bool = RuntimeField(default=True, strict=True)
    monitoring: bool = RuntimeField(default=True, strict=True)
