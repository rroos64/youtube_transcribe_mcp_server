import importlib

import mcp_server.app as mcp_app


class RecordingMCP:
    def __init__(self) -> None:
        self.tools = []
        self.resources = []
        self.prompts = []

    def tool(self, func=None, **_kwargs):
        if func is None:
            return lambda f: self._record_tool(f)
        return self._record_tool(func)

    def resource(self, path: str, **_kwargs):
        def decorator(func):
            self.resources.append((path, func))
            return func

        return decorator

    def prompt(self, name_or_fn=None, **_kwargs):
        if callable(name_or_fn):
            return self._record_prompt(name_or_fn)

        def decorator(func):
            name = name_or_fn if isinstance(name_or_fn, str) else func.__name__
            self.prompts.append((name, func))
            return func

        return decorator

    def _record_tool(self, func):
        self.tools.append(func)
        return func

    def _record_prompt(self, func):
        self.prompts.append((func.__name__, func))
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
    prompt_names = {name for name, _ in recorder.prompts}

    assert "youtube_transcribe" in tool_names
    assert "read_file_chunk" in tool_names
    assert any(path.startswith("transcripts://") for path in resource_paths)
    assert any(path.startswith("template://") for path in resource_paths)
    assert "summary" in prompt_names
