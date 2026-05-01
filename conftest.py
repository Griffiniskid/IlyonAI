"""Bootstrap test discovery: expose IlyonAi-Wallet-assistant-main/server on sys.path."""
from __future__ import annotations

import sys
import types
from pathlib import Path

_HERE = Path(__file__).parent
_ASSISTANT_SERVER = _HERE / "IlyonAi-Wallet-assistant-main" / "server"
if str(_ASSISTANT_SERVER) not in sys.path:
    sys.path.insert(0, str(_ASSISTANT_SERVER))


# Provide an importable alias so user code can write
# `from IlyonAi_Wallet_assistant_main.server.app...`.
def _alias_assistant_package() -> None:
    server_pkg = _ASSISTANT_SERVER

    grand = types.ModuleType("IlyonAi_Wallet_assistant_main")
    grand.__path__ = []  # type: ignore[attr-defined]
    sys.modules.setdefault("IlyonAi_Wallet_assistant_main", grand)

    parent = types.ModuleType("IlyonAi_Wallet_assistant_main.server")
    parent.__path__ = [str(server_pkg)]  # type: ignore[attr-defined]
    sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server", parent)

    app_mod = types.ModuleType("IlyonAi_Wallet_assistant_main.server.app")
    app_mod.__path__ = [str(server_pkg / "app")]  # type: ignore[attr-defined]
    sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server.app", app_mod)


_alias_assistant_package()
