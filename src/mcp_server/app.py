try:
    from fastmcp import Context, FastMCP
except ModuleNotFoundError as exc:
    if exc.name not in (None, "fastmcp") and str(exc) != "fastmcp":
        raise

    _fastmcp_import_error = exc

    class Context:  # type: ignore[override]
        pass

    class PromptToolMiddleware:  # type: ignore[override]
        pass

    class FastMCP:  # type: ignore[override]
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def tool(self, func=None, **_kwargs):
            if func is None:
                return lambda f: f
            return func

        def resource(self, _path, **_kwargs):
            return lambda f: f

        def prompt(self, name_or_fn=None, **_kwargs):
            if callable(name_or_fn):
                return name_or_fn
            return lambda f: f

        def add_middleware(self, *_args, **_kwargs) -> None:
            return None

        def run(self, *args, **kwargs) -> None:  # pragma: no cover
            raise RuntimeError(
                "fastmcp is required to run the server. Install it with "
                "`pip install -r requirements.txt`."
            ) from _fastmcp_import_error
else:
    try:
        from fastmcp.server.middleware.tool_injection import PromptToolMiddleware
    except ModuleNotFoundError:
        PromptToolMiddleware = None


# FastMCP v2.14.x uses `stateless_http` (not `stateless`)
mcp = FastMCP(
    "yt-dlp-transcriber",
    instructions=(
        "Fetches YouTube subtitles via yt-dlp and returns cleaned transcripts. "
        "Use youtube_get_duration for metadata, youtube_transcribe_auto to choose text vs file "
        "output, or youtube_transcribe_to_file for file output and read_file_chunk/read_file_info "
        "to page. Storage is session-scoped under /data/<session_id>. Resources are available at "
        "transcripts://session/{session_id}/* and templates at template://transcript/*. "
        "Prompts are available as paragraphs, summary, translate, outline, quotes, faq, glossary, "
        "and action_items."
    ),
)

if PromptToolMiddleware is not None:
    mcp.add_middleware(PromptToolMiddleware())
