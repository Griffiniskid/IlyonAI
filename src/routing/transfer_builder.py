class TransferBuilder:
    async def build_evm(self, to_addr, amount_wei, from_addr, chain_id=1):
        return {
            "unsigned_tx": {"to": to_addr, "value": hex(amount_wei), "data": "0x"},
            "chain_id": chain_id,
        }

    async def build_solana(self, to_addr, amount_lamports, from_addr):
        return {
            "unsigned_tx": {"to": to_addr, "amount": amount_lamports},
            "chain": "solana",
        }
