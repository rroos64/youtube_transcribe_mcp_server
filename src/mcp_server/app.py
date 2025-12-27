try:
    from fastmcp import FastMCP
except ModuleNotFoundError as exc:
    if exc.name not in (None, "fastmcp") and str(exc) != "fastmcp":
        raise

    _fastmcp_import_error = exc

    class FastMCP:  # type: ignore[override]
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def tool(self, func=None):
            if func is None:
                return lambda f: f
            return func

        def resource(self, _path):
            return lambda f: f

        def run(self, *args, **kwargs) -> None:  # pragma: no cover
            raise RuntimeError(
                "fastmcp is required to run the server. Install it with "
                "`pip install -r requirements.txt`."
            ) from _fastmcp_import_error


# FastMCP v2.14.x uses `stateless_http` (not `stateless`)
mcp = FastMCP(
    "yt-dlp-transcriber",
    instructions=(
        "Fetches YouTube subtitles via yt-dlp and returns cleaned transcripts. "
        "Use youtube_get_duration for metadata, youtube_transcribe_auto to choose text vs file "
        "output, or youtube_transcribe_to_file for file output and read_file_chunk/read_file_info "
        "to page. Storage is session-scoped under /data/<session_id>. Resources are available at "
        "transcripts://session/{session_id}/* and templates at template://transcript/*."
    ),
)
