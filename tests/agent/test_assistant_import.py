def test_can_import_crypto_agent():
    from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
        _build_swap_tx,
    )
    assert callable(_build_swap_tx)


def test_can_import_transfer_builder():
    from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
        _build_transfer_transaction,
    )
    assert callable(_build_transfer_transaction)
