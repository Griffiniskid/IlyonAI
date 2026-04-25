from typing import Optional
from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    user_address: str = Field(..., description="Connected EVM wallet address of the caller (MetaMask or Phantom EVM)")
    solana_address: Optional[str] = Field(None, description="Connected Solana wallet address (Phantom)")
    query: str = Field(..., description="Natural-language question or command for the agent")
    chain_id: int = Field(..., description="Active chain identifier (EIP-155 for EVM, 101 for Solana frontend context)")
    session_id: str = Field(..., description="Unique session identifier for conversation continuity")
    chat_id: Optional[str] = Field(None, description="Existing chat ID to continue (null = new chat)")
    wallet_type: Optional[str] = Field(None, description="Connected wallet type: metamask or phantom")
