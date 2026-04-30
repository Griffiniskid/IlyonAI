from pathlib import Path


def test_agent_api_uses_explicit_node_proxy_route():
    route = Path("web/app/api/v1/agent/route.ts")

    assert route.exists()
    content = route.read_text()
    assert 'runtime = "nodejs"' in content
    assert "ASSISTANT_API_TARGET" in content
    assert "/api/v1/agent" in content
    assert "AbortSignal.timeout" in content
