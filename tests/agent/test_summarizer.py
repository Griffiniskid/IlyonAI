import pytest
from src.agent.summarizer import maybe_summarize


class FakeRouter:
    async def complete(self, **kw):
        return {"content": "Summary of conversation"}


class FakeGreenfield:
    def __init__(self):
        self.writes = []

    async def put_object(self, key, body):
        self.writes.append({"key": key, "body": body})

    async def get_object(self, key):
        return None
