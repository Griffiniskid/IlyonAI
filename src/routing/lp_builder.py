class LpBuilder:
    async def build(
        self, protocol, token_a, token_b, amount_a, amount_b, user_addr, chain_id=1
    ):
        return {
            "unsigned_tx": {"to": "0xlp", "data": "0x"},
            "protocol": protocol,
            "assets": [token_a, token_b],
        }
