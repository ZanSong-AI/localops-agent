from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


LOCAL_PRIVACY = {"private", "sensitive"}
CLOUD_SAFE_PRIVACY = {"public", "sanitized"}


@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    reason: str


def choose_route(
    privacy: str,
    depth: str,
    routine_model: str,
    deep_model: str,
    request_cloud: bool = False,
    allow_cloud: bool = False,
    cloud_model: Optional[str] = None,
) -> Route:
    if privacy not in LOCAL_PRIVACY | CLOUD_SAFE_PRIVACY:
        raise ValueError("privacy must be private, sensitive, public, or sanitized")
    if depth not in {"routine", "deep"}:
        raise ValueError("depth must be routine or deep")
    if request_cloud:
        if privacy not in CLOUD_SAFE_PRIVACY:
            raise PermissionError("private or sensitive content cannot use the cloud route")
        if not allow_cloud:
            raise PermissionError("cloud route requires explicit --allow-cloud")
        if not cloud_model:
            raise RuntimeError("LOCALOPS_CLOUD_MODEL is not configured")
        return Route("cloud", cloud_model, "explicit cloud request for public/sanitized content")
    if depth == "deep":
        return Route("ollama", deep_model, "explicit high-value local review")
    return Route("ollama", routine_model, "default local routine processing")
