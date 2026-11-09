"""Unit tests for the web hook tools (no live AbraFlexi needed)."""
import asyncio
import json
from unittest import mock

import pytest

from abraflexi_mcp_server import server

HOOK_TOOLS = [
    "webhook_list",
    "webhook_get",
    "webhook_register",
    "webhook_unregister",
    "webhook_retry",
]


class FakeClient:
    """Stand-in for python_abraflexi.ReadWrite recording the HTTP calls."""

    def __init__(self, result=None, raises=None, last_response_code=200, text=""):
        self.default_url_params = {}
        self.calls = []
        self._result = {"hooks": []} if result is None else result
        self._raises = raises
        self.last_response_code = last_response_code
        self.last_response = mock.Mock(text=text)

    def perform_request(self, suffix="", method="GET", *a, **kw):
        self.calls.append((suffix, method, dict(self.default_url_params)))
        if self._raises:
            raise self._raises
        return self._result


@pytest.fixture(autouse=True)
def writable(monkeypatch):
    monkeypatch.setenv("READ_ONLY", "false")
    monkeypatch.setattr(server, "get_abraflexi_config", lambda: {"url": "https://x", "company": "c"})


def patch_client(client):
    return mock.patch.object(server, "ReadWrite", return_value=client)


def test_tools_registered_with_title_and_all_annotation_hints():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in HOOK_TOOLS:
        tool = tools[name]
        assert tool.title and tool.title != name
        ann = tool.annotations
        for hint in ("read_only_hint", "destructive_hint", "idempotent_hint", "open_world_hint"):
            assert getattr(ann, hint) is not None, f"{name}: {hint} not set"
        assert not (ann.read_only_hint and ann.destructive_hint)
        for pname, schema in tool.parameters.get("properties", {}).items():
            assert schema.get("description"), f"{name}.{pname} has no description"


def test_list_and_get_are_read_only_and_unregister_is_destructive():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert tools["webhook_list"].annotations.read_only_hint is True
    assert tools["webhook_get"].annotations.read_only_hint is True
    assert tools["webhook_unregister"].annotations.destructive_hint is True


def test_list_calls_hooks_endpoint():
    client = FakeClient(result={"hooks": [{"id": 3, "url": "https://r/h"}]})
    with patch_client(client):
        out = json.loads(server.webhook_list())
    assert out["hooks"][0]["id"] == 3
    assert client.calls == [("", "GET", {})]


def test_register_sends_documented_parameters():
    client = FakeClient(result={"success": "true"})
    with patch_client(client):
        server.webhook_register(
            url="https://example.com/hook", format="JSON", sec_key="s3cret",
            last_version=7, skip_url_test=True,
        )
    suffix, method, params = client.calls[0]
    assert (suffix, method) == ("", "PUT")
    assert params == {
        "url": "https://example.com/hook", "format": "JSON",
        "secKey": "s3cret", "lastVersion": 7, "skipUrlTest": "true",
    }


def test_register_minimal_omits_optional_parameters():
    client = FakeClient()
    with patch_client(client):
        server.webhook_register(url="https://example.com/hook")
    assert client.calls[0][2] == {"url": "https://example.com/hook", "format": "JSON"}


@pytest.mark.parametrize("bad", ["ftp://x/h", "javascript:alert(1)", "https://user:pw@host/h", "http:///nohost", "not a url"])
def test_register_rejects_unsafe_urls(bad):
    with patch_client(FakeClient()) as p:
        with pytest.raises(ValueError):
            server.webhook_register(url=bad)
    p.assert_not_called()


def test_unregister_and_retry_paths():
    client = FakeClient(result=True)
    with patch_client(client):
        server.webhook_unregister(id=5)
        server.webhook_retry(id=5)
        server.webhook_get(id=5)
    assert [c[:2] for c in client.calls] == [
        ("5.json", "DELETE"), ("5/retry.json", "PUT"), ("5.json", "GET"),
    ]


def test_write_tools_blocked_in_read_only_mode(monkeypatch):
    monkeypatch.setenv("READ_ONLY", "true")
    with patch_client(FakeClient()) as p:
        for fn, kw in (
            (server.webhook_register, {"url": "https://example.com/h"}),
            (server.webhook_unregister, {"id": 1}),
            (server.webhook_retry, {"id": 1}),
        ):
            with pytest.raises(ValueError, match="read-only"):
                fn(**kw)
    p.assert_not_called()


def test_sec_key_never_appears_in_output():
    client = FakeClient(result={"hooks": [{"id": 1, "secKey": "topsecret", "url": "https://r/h"}]})
    with patch_client(client):
        assert "topsecret" not in server.webhook_list()
        assert "topsecret" not in server.webhook_get(id=1)


def test_sec_key_is_masked_in_error_messages():
    err = server.AbraFlexiException("HTTP 400: cannot call https://r/h?secKey=topsecret")
    client = FakeClient(raises=err)
    with patch_client(client):
        with pytest.raises(ValueError) as exc:
            server.webhook_register(url="https://r/h", sec_key="topsecret")
    assert "topsecret" not in str(exc.value)


def test_hooks_disabled_gives_actionable_message():
    client = FakeClient(result=False, last_response_code=400,
                        text="Hooks are not enabled in flexibee-server.xml")
    with patch_client(client):
        with pytest.raises(ValueError, match="enableHooks"):
            server.webhook_list()
