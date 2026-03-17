import importlib


def test_monetization_package_imports_without_missing_legacy_symbols():
    module = importlib.import_module("src.monetization")
    assert callable(module.get_manager)
