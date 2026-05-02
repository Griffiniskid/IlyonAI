"""Bootstrap import aliases for wallet assistant package."""
import sys
import types

# Create alias module with underscores for hyphenated directory
grand = types.ModuleType("IlyonAi_Wallet_assistant_main")
grand.__path__ = []
sys.modules.setdefault("IlyonAi_Wallet_assistant_main", grand)

parent = types.ModuleType("IlyonAi_Wallet_assistant_main.server")
parent.__path__ = ["/app/IlyonAi-Wallet-assistant-main/server"]
sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server", parent)
grand.server = parent

app_mod = types.ModuleType("IlyonAi_Wallet_assistant_main.server.app")
app_mod.__path__ = ["/app/IlyonAi-Wallet-assistant-main/server/app"]
sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server.app", app_mod)
parent.app = app_mod

agents_mod = types.ModuleType("IlyonAi_Wallet_assistant_main.server.app.agents")
agents_mod.__path__ = ["/app/IlyonAi-Wallet-assistant-main/server/app/agents"]
sys.modules.setdefault("IlyonAi_Wallet_assistant_main.server.app.agents", agents_mod)
app_mod.agents = agents_mod
