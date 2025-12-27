import importlib

import mcp_server.app as mcp_app


class RecordingMCP:
    def __init__(self) -> None:
        self.tools = []
        self.resources = []

    def tool(self, func=None):
        if func is None:
            return lambda f: self._record_tool(f)
        return self._record_tool(func)

    def resource(self, path: str):
        def decorator(func):
            self.resources.append((path, func))
            return func

        return decorator

    def _record_tool(self, func):
        self.tools.append(func)
        return func


def test_mcp_wiring_registers_tools_and_resources(monkeypatch):
    recorder = RecordingMCP()
    monkeypatch.setattr(mcp_app, "mcp", recorder)

    import mcp_server.tools as tools
    import mcp_server.resources as resources
    import mcp_server.templates as templates

    importlib.reload(tools)
    importlib.reload(resources)
    importlib.reload(templates)

    tool_names = {tool.__name__ for tool in recorder.tools}
    resource_paths = {path for path, _ in recorder.resources}

    assert "youtube_transcribe" in tool_names
    assert "read_file_chunk" in tool_names
    assert any(path.startswith("transcripts://") for path in resource_paths)
    assert any(path.startswith("template://") for path in resource_paths)
