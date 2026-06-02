"""Bootstrap import aliases for the wallet-assistant package.

The wallet-assistant lives in `IlyonAi-Wallet-assistant-main/` (hyphens), which
Python cannot import by name. Code across the agent tools imports it as
`IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent` (underscores);
this module wires that alias to the REAL directory so those imports resolve.

Paths are resolved relative to the repo (works locally) with a Docker fallback
(`/app/...`). The previous version hardcoded only the Docker paths, so every
underscore import failed locally with ModuleNotFoundError on `.crypto_agent`.
"""
import sys
import types
from pathlib import Path

# Locate the wallet-assistant server dir: repo-relative first, Docker fallback.
_repo_root = Path(__file__).resolve().parents[1]
_candidates = [
    _repo_root / "IlyonAi-Wallet-assistant-main" / "server",
    Path("/app/IlyonAi-Wallet-assistant-main/server"),
]
_server = next((p for p in _candidates if p.exists()), _candidates[0])
_server_str = str(_server)

# crypto_agent.py itself does `from app.core.config import …`, so the server dir
# must be importable as a top-level path.
if _server_str not in sys.path:
    sys.path.insert(0, _server_str)

# Create alias modules with underscores for the hyphenated directory, each with
# a real __path__ so Python can load their submodules (crypto_agent, etc.).
grand = types.ModuleType("IlyonAi_Wallet_assistant_main")
grand.__path__ = []
sys.modules.setdefault("IlyonAi_Wallet_assistant_main", grand)

parent = types.ModuleType("IlyonAi_Wallet_assistant_main.server")
parent.__path__ = [_server_str]
sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server", parent)
grand.server = parent

app_mod = types.ModuleType("IlyonAi_Wallet_assistant_main.server.app")
app_mod.__path__ = [str(_server / "app")]
sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server.app", app_mod)
parent.app = app_mod

agents_mod = types.ModuleType("IlyonAi_Wallet_assistant_main.server.app.agents")
agents_mod.__path__ = [str(_server / "app" / "agents")]
sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server.app.agents", agents_mod)
app_mod.agents = agents_mod
