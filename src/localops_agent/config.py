from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


VOICE_MEMOS_DEFAULT = Path(
    "~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/"
).expanduser()


@dataclass(frozen=True)
class Config:
    root: Path
    state_dir: Path
    database: Path
    intake_repo: Path
    voice_memos: Path
    local_endpoint: str
    routine_model: str
    deep_model: str
    cloud_endpoint: Optional[str]
    cloud_model: Optional[str]

    @classmethod
    def load(cls, root: Optional[Path] = None, state_dir: Optional[Path] = None) -> "Config":
        project_root = (root or Path(__file__).resolve().parents[2]).resolve()
        state = (state_dir or Path(os.environ.get("LOCALOPS_STATE_DIR", project_root / ".localops"))).expanduser().resolve()
        return cls(
            root=project_root,
            state_dir=state,
            database=state / "localops.sqlite3",
            intake_repo=project_root / "skills" / "intake-skill",
            voice_memos=Path(os.environ.get("LOCALOPS_VOICE_MEMOS", str(VOICE_MEMOS_DEFAULT))).expanduser().resolve(),
            local_endpoint=os.environ.get("LOCALOPS_OLLAMA_ENDPOINT", "http://127.0.0.1:11434"),
            routine_model=os.environ.get("LOCALOPS_ROUTINE_MODEL", "song-local"),
            deep_model=os.environ.get("LOCALOPS_DEEP_MODEL", "song-deep"),
            cloud_endpoint=os.environ.get("LOCALOPS_CLOUD_ENDPOINT"),
            cloud_model=os.environ.get("LOCALOPS_CLOUD_MODEL"),
        )

    def ensure_state(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "documents").mkdir(exist_ok=True)
        (self.state_dir / "analyses").mkdir(exist_ok=True)
        (self.state_dir / "exports").mkdir(exist_ok=True)
        (self.state_dir / "agent_runs").mkdir(exist_ok=True)
        (self.state_dir / "context").mkdir(exist_ok=True)
