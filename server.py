import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from fastmcp import FastMCP

# FastMCP v2.14.x uses `stateless_http` (not `stateless`)
mcp = FastMCP(
    "yt-dlp-transcriber",
    instructions=(
        "Fetches YouTube subtitles via yt-dlp and returns cleaned transcripts. "
        "Use youtube_get_duration for metadata, youtube_transcribe_auto to choose text vs file "
        "output, or youtube_transcribe_to_file for large outputs and read_file_chunk/read_file_info "
        "to page. File outputs require a client-provided session_id."
    ),
    stateless_http=True,
)

# ---------- Config ----------
YTDLP_BIN = os.environ.get("YTDLP_BIN", "yt-dlp")
PLAYER_CLIENT = os.environ.get("YTDLP_PLAYER_CLIENT", "web_safari")
REMOTE_EJS = os.environ.get("YTDLP_REMOTE_EJS", "ejs:github")
SUB_LANG = os.environ.get("YTDLP_SUB_LANG", "en.*")
TIMEOUT_SEC = int(os.environ.get("YTDLP_TIMEOUT_SEC", "180"))
AUTO_TEXT_MAX_BYTES = int(os.environ.get("AUTO_TEXT_MAX_BYTES", "200000"))
DEFAULT_TTL_SEC = int(os.environ.get("DEFAULT_TTL_SEC", "3600"))

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_YT_URL_RE = re.compile(r"^https?://(www\.)?youtube\.com/watch\?v=|^https?://youtu\.be/")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# ---------- Helpers ----------
def _is_youtube_url(url: str) -> bool:
    return bool(_YT_URL_RE.search(url))


def _validate_session_id(session_id: str) -> str:
    if not session_id or not _SESSION_ID_RE.match(session_id):
        raise ValueError("session_id must be 1-64 chars of letters, numbers, '-' or '_'")
    return session_id


def _session_dir(session_id: str) -> Path:
    session_id = _validate_session_id(session_id)
    p = DATA_DIR / session_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _meta_dir(session_id: str) -> Path:
    d = _session_dir(session_id) / ".meta"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_within_data_dir(p: Path) -> bool:
    try:
        p.resolve().relative_to(DATA_DIR.resolve())
        return True
    except ValueError:
        return False


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (DATA_DIR / p).resolve()
    else:
        p = p.resolve()

    if not _is_within_data_dir(p):
        raise ValueError("path must be within DATA_DIR")
    return p


def _make_handle() -> str:
    return f"tr_{uuid.uuid4().hex}"


def _expires_at(ttl_seconds: int) -> str:
    return (datetime.utcnow() + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat() + "Z"


def _write_meta(
    session_id: str, handle: str, relpath: str, expires_at: str | None, persisted: bool, fmt: str
) -> Path:
    meta = {
        "handle": handle,
        "session_id": session_id,
        "relpath": relpath,
        "expires_at": expires_at,
        "persisted": persisted,
        "fmt": fmt,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }
    meta_path = _meta_dir(session_id) / f"{handle}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta_path


def _load_meta(session_id: str, handle: str) -> dict:
    meta_path = _meta_dir(session_id) / f"{handle}.json"
    if not meta_path.exists():
        raise ValueError(f"Handle not found: {handle}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _is_expired(expires_at: str) -> bool:
    try:
        ts = expires_at[:-1] if expires_at.endswith("Z") else expires_at
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return True
    return datetime.utcnow() >= dt


def _cleanup_expired(session_id: str | None = None) -> int:
    if session_id is not None:
        meta_paths = _meta_dir(session_id).glob("*.json")
    else:
        meta_paths = DATA_DIR.glob("*/.meta/*.json")

    removed = 0
    for meta_path in meta_paths:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if meta.get("persisted"):
            continue

        expires_at = meta.get("expires_at")
        if not expires_at or not _is_expired(expires_at):
            continue

        relpath = meta.get("relpath")
        if relpath:
            target = (DATA_DIR / relpath).resolve()
            if _is_within_data_dir(target) and target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass

        try:
            meta_path.unlink()
        except OSError:
            pass
        removed += 1

    return removed


def _resolve_handle(session_id: str, handle: str) -> tuple[Path, dict]:
    session_id = _validate_session_id(session_id)
    _cleanup_expired(session_id)
    meta = _load_meta(session_id, handle)

    if not meta.get("persisted") and meta.get("expires_at") and _is_expired(meta["expires_at"]):
        relpath = meta.get("relpath")
        if relpath:
            target = (DATA_DIR / relpath).resolve()
            if _is_within_data_dir(target) and target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
        try:
            (_meta_dir(session_id) / f"{handle}.json").unlink()
        except OSError:
            pass
        raise ValueError("Transcript expired; request a new transcription.")

    relpath = meta.get("relpath")
    if not relpath:
        raise ValueError("Handle metadata missing relpath.")

    p = (DATA_DIR / relpath).resolve()
    if not _is_within_data_dir(p):
        raise ValueError("Resolved path is outside DATA_DIR.")
    if not p.exists():
        raise ValueError(f"File does not exist: {p}")

    return p, meta


def _vtt_to_lines(vtt: str) -> list[str]:
    """
    Convert YouTube WebVTT variants to plain text lines.
    Handles:
      - WEBVTT metadata
      - cue timing lines: 00:00:01.000 --> 00:00:03.000
      - inline timestamps: <00:00:00.400>
      - <c>...</c> tags (including class variants)
      - any other leftover tags
      - normalizes whitespace
    """
    out_lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line:
            continue

        # Drop headers/metadata
        if line.startswith(("WEBVTT", "NOTE", "STYLE", "REGION", "Kind:", "Language:")):
            continue

        # Drop cue timing lines
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s-->\s", line):
            continue

        # Remove inline timestamps like <00:00:00.400>
        line = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", "", line)

        # Remove <c> tags, including <c.colorE5E5E5>
        line = re.sub(r"</?c(\.[^>]*)?>", "", line)

        # Remove any remaining HTML-ish tags
        line = re.sub(r"</?[^>]+>", "", line)

        # Normalize whitespace
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            out_lines.append(line)

    return out_lines


def _dedupe_lines(lines: list[str], window: int = 6) -> list[str]:
    """
    Removes duplicates:
      - always removes consecutive duplicates
      - also removes duplicates seen recently within a small rolling window
    This addresses YouTube "rollover" captions + en/en-orig duplication patterns.
    """
    deduped: list[str] = []
    recent: list[str] = []
    prev: str | None = None

    for l in lines:
        if l == prev:
            continue
        if l in recent:
            continue
        deduped.append(l)
        recent.append(l)
        if len(recent) > window:
            recent = recent[-window:]
        prev = l

    return deduped


def _vtt_to_text(vtt: str) -> str:
    lines = _vtt_to_lines(vtt)
    lines = _dedupe_lines(lines, window=6)
    return "\n".join(lines).strip()


def _run_ytdlp_info(url: str) -> dict:
    """
    Runs yt-dlp to fetch metadata only (no download).
    Returns a parsed JSON dict.
    """
    cmd = [
        YTDLP_BIN,
        "--remote-components",
        REMOTE_EJS,
        "--extractor-args",
        f"youtube:player_client={PLAYER_CLIENT}",
        "--skip-download",
        "--no-progress",
        "--no-playlist",
        "--dump-json",
        url,
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=TIMEOUT_SEC,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed (code {proc.returncode}). Output:\n{proc.stdout}")

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    json_line = None
    for line in reversed(lines):
        if line.lstrip().startswith("{") and line.rstrip().endswith("}"):
            json_line = line
            break

    if json_line is None:
        raise RuntimeError(f"yt-dlp metadata output missing JSON. Output:\n{proc.stdout}")

    try:
        return json.loads(json_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse yt-dlp metadata JSON: {exc}") from exc


def _run_ytdlp_subs(url: str) -> Dict[str, str]:
    """
    Runs yt-dlp to download English subtitles (VTT) into a temp dir.
    Returns {"vtt_text": ..., "stdout": ..., "picked_file": ...}
    """
    with tempfile.TemporaryDirectory(prefix="yt_transcribe_") as td:
        workdir = Path(td)

        cmd = [
            YTDLP_BIN,
            "--remote-components",
            REMOTE_EJS,
            "--extractor-args",
            f"youtube:player_client={PLAYER_CLIENT}",
            "--write-auto-subs",
            "--sub-lang",
            SUB_LANG,
            "--skip-download",
            "--no-progress",
            "--paths",
            str(workdir),
            url,
        ]

        proc = subprocess.run(
            cmd,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=TIMEOUT_SEC,
        )

        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp failed (code {proc.returncode}). Output:\n{proc.stdout}")

        # Prefer .en.vtt; fallback to any .vtt
        vtts = sorted(workdir.glob("*.en.vtt"))
        if not vtts:
            vtts = sorted(workdir.glob("*.vtt"))

        if not vtts:
            raise RuntimeError(f"No subtitle files were produced. yt-dlp output:\n{proc.stdout}")

        vtt_path = vtts[-1]
        vtt_text = vtt_path.read_text(encoding="utf-8", errors="replace")
        return {"vtt_text": vtt_text, "stdout": proc.stdout, "picked_file": vtt_path.name}


def _make_output_base(url: str, base_dir: Path | None = None) -> Path:
    if base_dir is None:
        base_dir = DATA_DIR
    vid_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return base_dir / f"youtube_{vid_hash}_{stamp}"


def _write_transcript(base: Path, fmt: str, transcript_txt: str, vtt_text: str) -> Path:
    if fmt == "vtt":
        out = base.with_suffix(".vtt")
        out.write_text(vtt_text, encoding="utf-8")
        return out

    if fmt == "txt":
        out = base.with_suffix(".txt")
        out.write_text(transcript_txt + "\n", encoding="utf-8")
        return out

    out = base.with_suffix(".jsonl")
    with out.open("w", encoding="utf-8") as f:
        for line in transcript_txt.splitlines():
            f.write(json.dumps({"text": line}, ensure_ascii=False) + "\n")
    return out


# ---------- MCP Tools ----------
@mcp.tool
def youtube_transcribe(url: str) -> str:
    """
    Returns plain transcript text (may still be large and subject to client truncation).
    Prefer youtube_transcribe_to_file + read_file_chunk for big transcripts.
    """
    if not _is_youtube_url(url):
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")

    res = _run_ytdlp_subs(url)
    transcript = _vtt_to_text(res["vtt_text"])

    if not transcript:
        raise RuntimeError(f"Subtitle file was empty after parsing ({res['picked_file']}).")
    return transcript


@mcp.tool
def youtube_transcribe_to_file(url: str, session_id: str, fmt: str = "txt") -> dict:
    """
    Saves transcript under /data/<session_id> and returns a handle object.
    fmt: "txt" | "vtt" | "jsonl"
    """
    if not _is_youtube_url(url):
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")
    if fmt not in ("txt", "vtt", "jsonl"):
        raise ValueError("fmt must be one of: txt, vtt, jsonl")

    session_id = _validate_session_id(session_id)
    _cleanup_expired(session_id)

    res = _run_ytdlp_subs(url)
    vtt_text = res["vtt_text"]
    transcript_txt = _vtt_to_text(vtt_text)

    base = _make_output_base(url, _session_dir(session_id))
    out = _write_transcript(base, fmt, transcript_txt, vtt_text)
    relpath = out.relative_to(DATA_DIR).as_posix()

    handle = _make_handle()
    expires_at = _expires_at(DEFAULT_TTL_SEC)
    _write_meta(session_id, handle, relpath, expires_at, False, fmt)

    return {
        "handle": handle,
        "session_id": session_id,
        "relpath": relpath,
        "expires_at": expires_at,
        "persisted": False,
        "fmt": fmt,
    }


@mcp.tool
def youtube_get_duration(url: str) -> dict:
    """
    Returns video duration metadata.
    """
    if not _is_youtube_url(url):
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")

    info = _run_ytdlp_info(url)
    return {
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string"),
        "title": info.get("title"),
        "is_live": info.get("is_live"),
    }


@mcp.tool
def youtube_transcribe_auto(
    url: str, fmt: str = "txt", max_text_bytes: int | None = None, session_id: str | None = None
) -> dict:
    """
    Returns transcript text if small enough; otherwise writes to /data/<session_id> and returns a handle.
    fmt: "txt" | "vtt" | "jsonl"
    """
    if not _is_youtube_url(url):
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")
    if fmt not in ("txt", "vtt", "jsonl"):
        raise ValueError("fmt must be one of: txt, vtt, jsonl")

    if max_text_bytes is None:
        max_text_bytes = AUTO_TEXT_MAX_BYTES
    if max_text_bytes < 1:
        raise ValueError("max_text_bytes must be >= 1")

    info = _run_ytdlp_info(url)
    duration = info.get("duration")
    duration_string = info.get("duration_string")
    title = info.get("title")
    is_live = info.get("is_live")

    res = _run_ytdlp_subs(url)
    vtt_text = res["vtt_text"]
    transcript_txt = _vtt_to_text(vtt_text)

    if not transcript_txt:
        raise RuntimeError(f"Subtitle file was empty after parsing ({res['picked_file']}).")

    text_bytes = len(transcript_txt.encode("utf-8"))
    if text_bytes <= max_text_bytes:
        return {
            "kind": "text",
            "text": transcript_txt,
            "bytes": text_bytes,
            "duration": duration,
            "duration_string": duration_string,
            "title": title,
            "is_live": is_live,
        }

    if not session_id:
        raise ValueError("session_id is required when transcript exceeds max_text_bytes")

    session_id = _validate_session_id(session_id)
    _cleanup_expired(session_id)

    base = _make_output_base(url, _session_dir(session_id))
    out = _write_transcript(base, fmt, transcript_txt, vtt_text)
    relpath = out.relative_to(DATA_DIR).as_posix()
    handle = _make_handle()
    expires_at = _expires_at(DEFAULT_TTL_SEC)
    _write_meta(session_id, handle, relpath, expires_at, False, fmt)

    return {
        "kind": "file",
        "handle": handle,
        "session_id": session_id,
        "relpath": relpath,
        "expires_at": expires_at,
        "persisted": False,
        "bytes": text_bytes,
        "fmt": fmt,
        "duration": duration,
        "duration_string": duration_string,
        "title": title,
        "is_live": is_live,
    }


@mcp.tool
def read_file_info(path: str | None = None, handle: str | None = None, session_id: str | None = None) -> dict:
    """
    Returns file size and normalized path.
    Provide either (handle + session_id) or path.
    """
    if handle:
        if not session_id:
            raise ValueError("session_id is required when using handle")
        p, meta = _resolve_handle(session_id, handle)
        size = p.stat().st_size
        resp = {
            "handle": handle,
            "session_id": session_id,
            "path": str(p),
            "relpath": meta.get("relpath"),
            "size": size,
            "persisted": bool(meta.get("persisted")),
        }
        if meta.get("expires_at"):
            resp["expires_at"] = meta["expires_at"]
        return resp

    if not path:
        raise ValueError("Provide either handle+session_id or path")

    _cleanup_expired()
    p = _resolve_path(path)
    if not p.exists():
        raise ValueError(f"File does not exist: {p}")

    return {"path": str(p), "size": p.stat().st_size}


@mcp.tool
def read_file_chunk(
    path: str | None = None,
    offset: int = 0,
    max_bytes: int = 200000,
    handle: str | None = None,
    session_id: str | None = None,
) -> dict:
    """
    Reads a chunk of a saved transcript file (for clients with output limits).
    Provide either (handle + session_id) or path.
    Returns: { data, next_offset, eof, size, path }
    """
    if handle:
        if not session_id:
            raise ValueError("session_id is required when using handle")
        p, _meta = _resolve_handle(session_id, handle)
    else:
        if not path:
            raise ValueError("Provide either handle+session_id or path")
        _cleanup_expired()
        p = _resolve_path(path)

    if not p.exists():
        raise ValueError(f"File does not exist: {p}")
    if max_bytes < 1 or max_bytes > 200000:
        raise ValueError("max_bytes must be between 1 and 200000")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    size = p.stat().st_size
    if offset >= size:
        return {
            "data": "",
            "next_offset": offset,
            "eof": True,
            "size": size,
            "path": str(p),
        }

    with p.open("rb") as f:
        f.seek(offset)
        chunk = f.read(max_bytes)

    next_offset = offset + len(chunk)
    eof = next_offset >= size

    return {
        "data": chunk.decode("utf-8", errors="replace"),
        "next_offset": next_offset,
        "eof": eof,
        "size": size,
        "path": str(p),
    }


# ---------- Run Server ----------
if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        path="/mcp",
        stateless_http=True,
    )
