import openai
import pytest


@pytest.fixture(autouse=True)
def no_real_openai_client(monkeypatch):
    def refuse(self, *args, **kwargs):
        pytest.fail("a test constructed openai.OpenAI; pass a FakeClient instead")

    monkeypatch.setattr(openai.OpenAI, "__init__", refuse)
