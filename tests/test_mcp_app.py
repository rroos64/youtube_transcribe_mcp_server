import builtins
import importlib.util
from pathlib import Path


def test_app_fallback_when_fastmcp_missing(monkeypatch):
    app_path = Path(__file__).resolve().parents[1] / "src/mcp_server/app.py"
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fastmcp":
            raise ModuleNotFoundError("fastmcp")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    spec = importlib.util.spec_from_file_location("mcp_app_fallback", app_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    client = module.FastMCP("stub")

    def sample():
        return "ok"

    assert client.tool(sample) is sample
    assert client.tool()(sample) is sample
    assert client.resource("path")(sample) is sample
