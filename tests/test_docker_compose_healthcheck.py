from pathlib import Path


def test_web_healthcheck_uses_ipv4_loopback():
    compose = Path(__file__).resolve().parents[1] / "docker-compose.yml"

    content = compose.read_text()

    assert "http://127.0.0.1:3000" in content
    assert "http://localhost:3000" not in content
