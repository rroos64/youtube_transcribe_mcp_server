from fastmcp import FastMCP


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
