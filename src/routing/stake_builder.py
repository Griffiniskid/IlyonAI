"""Dispatches stake tx building per protocol (Lido, Rocket Pool, Jito, Marinade)."""


class StakeBuilder:
    async def build(self, protocol, amount, user_addr, chain_id=1):
        protocols = {
            "lido": self._lido,
            "rocket_pool": self._rocket,
            "jito": self._jito,
            "marinade": self._marinade,
        }
        fn = protocols.get(protocol.lower())
        if not fn:
            raise ValueError(f"Unknown staking protocol: {protocol}")
        return await fn(amount, user_addr, chain_id)

    async def _lido(self, amount, addr, chain_id):
        return {
            "unsigned_tx": {
                "to": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
                "value": hex(amount),
                "data": "0x",
            },
            "protocol": "lido",
            "asset": "ETH",
        }

    async def _rocket(self, amount, addr, chain_id):
        return {
            "unsigned_tx": {
                "to": "0xDD3b16e32452fE8a32d1993a29FdE93D6930e6C2",
                "value": hex(amount),
                "data": "0x",
            },
            "protocol": "rocket_pool",
            "asset": "ETH",
        }

    async def _jito(self, amount, addr, chain_id):
        return {
            "unsigned_tx": {
                "to": "J1to1P1ZYLv3shRP6vahQJ3jjwhQY2H6J6qjpswN1oX",
                "data": "0x",
            },
            "protocol": "jito",
            "asset": "SOL",
        }

    async def _marinade(self, amount, addr, chain_id):
        return {
            "unsigned_tx": {
                "to": "MarBmsSgKXdrN1egZEfNbPbRoyaw5pv1HCLtF7LkiA8",
                "data": "0x",
            },
            "protocol": "marinade",
            "asset": "SOL",
        }
