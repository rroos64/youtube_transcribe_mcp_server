import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

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

# ---------- Config ----------
YTDLP_BIN = os.environ.get("YTDLP_BIN", "yt-dlp")
PLAYER_CLIENT = os.environ.get("YTDLP_PLAYER_CLIENT", "web_safari")
REMOTE_EJS = os.environ.get("YTDLP_REMOTE_EJS", "ejs:github")
SUB_LANG = os.environ.get("YTDLP_SUB_LANG", "en.*")
TIMEOUT_SEC = int(os.environ.get("YTDLP_TIMEOUT_SEC", "180"))
AUTO_TEXT_MAX_BYTES = int(os.environ.get("AUTO_TEXT_MAX_BYTES", "200000"))
DEFAULT_TTL_SEC = int(os.environ.get("TRANSCRIPT_TTL_SECONDS", os.environ.get("DEFAULT_TTL_SEC", "3600")))
INLINE_TEXT_MAX_BYTES = int(os.environ.get("INLINE_TEXT_MAX_BYTES", "20000"))
MAX_SESSION_ITEMS = int(os.environ.get("MAX_SESSION_ITEMS", "0"))
MAX_SESSION_BYTES = int(os.environ.get("MAX_SESSION_BYTES", "0"))
DEFAULT_SESSION_ID = os.environ.get("DEFAULT_SESSION_ID", "")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

_YT_URL_RE = re.compile(r"^https?://(www\.)?youtube\.com/watch\?v=|^https?://youtu\.be/")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TRANSCRIPTS_DIR = "transcripts"
_DERIVED_DIR = "derived"
_MANIFEST_NAME = "manifest.json"

# ---------- Helpers ----------
def _is_youtube_url(url: str) -> bool:
    return bool(_YT_URL_RE.search(url))


def _validate_session_id(session_id: str) -> str:
    if not session_id or not _SESSION_ID_RE.match(session_id):
        raise ValueError("session_id must be 1-64 chars of letters, numbers, '-' or '_'")
    return session_id


def _extract_session_id(ctx: Any | None) -> str | None:
    if ctx is None:
        return None

    if isinstance(ctx, dict):
        for key in ("mcp-session-id", "mcp_session_id", "session_id", "sessionId"):
            val = ctx.get(key)
            if val:
                return str(val)

    for attr in ("session_id", "sessionId"):
        val = getattr(ctx, attr, None)
        if val:
            return str(val)

    headers = None
    if hasattr(ctx, "headers"):
        headers = getattr(ctx, "headers", None)
    elif hasattr(ctx, "request"):
        headers = getattr(getattr(ctx, "request", None), "headers", None)

    if headers is not None:
        for key in ("mcp-session-id", "MCP-Session-Id", "x-mcp-session-id"):
            if hasattr(headers, "get"):
                val = headers.get(key)
                if val:
                    return str(val)
    return None


def _get_session_id(session_id: str | None = None, ctx: Any | None = None) -> str:
    ctx_id = _extract_session_id(ctx)
    if session_id and ctx_id and session_id != ctx_id:
        raise ValueError("session_id does not match mcp-session-id header")
    if session_id:
        return _validate_session_id(session_id)
    if ctx_id:
        return _validate_session_id(ctx_id)
    if DEFAULT_SESSION_ID:
        return _validate_session_id(DEFAULT_SESSION_ID)
    raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _expires_at(ttl_seconds: int) -> str:
    return (datetime.utcnow() + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat() + "Z"


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        raw = ts[:-1] if ts.endswith("Z") else ts
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _is_within_root(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _session_root(session_id: str) -> Path:
    session_id = _validate_session_id(session_id)
    root = DATA_DIR / session_id
    root.mkdir(parents=True, exist_ok=True)
    (root / _TRANSCRIPTS_DIR).mkdir(parents=True, exist_ok=True)
    (root / _DERIVED_DIR).mkdir(parents=True, exist_ok=True)
    return root


def _transcripts_dir(session_id: str) -> Path:
    return _session_root(session_id) / _TRANSCRIPTS_DIR


def _derived_dir(session_id: str) -> Path:
    return _session_root(session_id) / _DERIVED_DIR


def _manifest_path(session_id: str) -> Path:
    return _session_root(session_id) / _MANIFEST_NAME


def _load_manifest(session_id: str) -> dict:
    path = _manifest_path(session_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}

    if not isinstance(data, dict):
        data = {}

    data.setdefault("session_id", session_id)
    data.setdefault("created_at", _now_iso())
    data.setdefault("items", [])
    if not isinstance(data["items"], list):
        data["items"] = []
    return data


def _save_manifest(session_id: str, manifest: dict) -> None:
    path = _manifest_path(session_id)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_id() -> str:
    return f"tr_{uuid.uuid4().hex}"


def _resolve_relpath(session_id: str, relpath: str) -> Path:
    if not relpath or relpath.startswith("/") or ".." in relpath.split("/"):
        raise ValueError("relpath must be a safe relative path")
    root = _session_root(session_id)
    p = (root / relpath).resolve()
    if not _is_within_root(p, root):
        raise ValueError("relpath resolves outside session directory")
    return p


def _item_sort_key(item: dict) -> tuple[datetime, str]:
    ts = _parse_ts(item.get("created_at")) or datetime.min
    return ts, item.get("id", "")


def _cleanup_session(session_id: str) -> int:
    session_id = _validate_session_id(session_id)
    manifest = _load_manifest(session_id)
    root = _session_root(session_id)

    kept: list[dict] = []
    removed = 0
    now = datetime.utcnow()
    changed = False

    for item in manifest.get("items", []):
        relpath = item.get("relpath")
        if not relpath:
            changed = True
            continue

        try:
            p = _resolve_relpath(session_id, relpath)
        except ValueError:
            changed = True
            continue

        if not p.exists():
            changed = True
            removed += 1
            continue

        pinned = bool(item.get("pinned"))
        expires_at = item.get("expires_at")
        expires_dt = _parse_ts(expires_at)
        if not pinned:
            if expires_dt is None:
                expires_at = _expires_at(DEFAULT_TTL_SEC)
                item["expires_at"] = expires_at
                expires_dt = _parse_ts(expires_at)
                changed = True

            if expires_dt and now >= expires_dt:
                try:
                    p.unlink()
                except OSError:
                    pass
                removed += 1
                changed = True
                continue

        item["size"] = p.stat().st_size
        kept.append(item)

    manifest["items"] = kept

    if MAX_SESSION_ITEMS > 0 or MAX_SESSION_BYTES > 0:
        total_size = sum(int(i.get("size") or 0) for i in kept)
        removable = sorted([i for i in kept if not i.get("pinned")], key=_item_sort_key)
        while removable and (
            (MAX_SESSION_ITEMS > 0 and len(kept) > MAX_SESSION_ITEMS)
            or (MAX_SESSION_BYTES > 0 and total_size > MAX_SESSION_BYTES)
        ):
            victim = removable.pop(0)
            try:
                vp = _resolve_relpath(session_id, victim.get("relpath", ""))
                if vp.exists():
                    vp.unlink()
            except (OSError, ValueError):
                pass
            total_size -= int(victim.get("size") or 0)
            kept.remove(victim)
            removed += 1
            changed = True

    if changed:
        _save_manifest(session_id, manifest)

    return removed


def _find_item(manifest: dict, item_id: str | None = None, relpath: str | None = None) -> dict | None:
    for item in manifest.get("items", []):
        if item_id and item.get("id") == item_id:
            return item
        if relpath and item.get("relpath") == relpath:
            return item
    return None


def _add_item(
    session_id: str,
    kind: str,
    fmt: str,
    relpath: str,
    pinned: bool,
    ttl_seconds: int,
) -> dict:
    manifest = _load_manifest(session_id)
    item_id = _make_id()
    created_at = _now_iso()
    expires_at = None if pinned else _expires_at(ttl_seconds)
    p = _resolve_relpath(session_id, relpath)
    size = p.stat().st_size

    item = {
        "id": item_id,
        "kind": kind,
        "format": fmt,
        "relpath": relpath,
        "size": size,
        "created_at": created_at,
        "expires_at": expires_at,
        "pinned": pinned,
    }
    manifest["items"].append(item)
    _save_manifest(session_id, manifest)
    _cleanup_session(session_id)
    return item


def _get_item(session_id: str, item_id: str | None = None, relpath: str | None = None) -> tuple[dict, Path]:
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id, relpath=relpath)
    if not item:
        raise ValueError("Item not found")
    p = _resolve_relpath(session_id, item.get("relpath", ""))
    if not p.exists():
        raise ValueError(f"File does not exist: {p}")
    return item, p


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
def youtube_transcribe_to_file(url: str, fmt: str = "txt", session_id: str | None = None, ctx: Any | None = None) -> dict:
    """
    Saves transcript under /data/<session_id>/transcripts and returns a manifest item object.
    fmt: "txt" | "vtt" | "jsonl"
    """
    if not _is_youtube_url(url):
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")
    if fmt not in ("txt", "vtt", "jsonl"):
        raise ValueError("fmt must be one of: txt, vtt, jsonl")

    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)

    res = _run_ytdlp_subs(url)
    vtt_text = res["vtt_text"]
    transcript_txt = _vtt_to_text(vtt_text)

    base = _make_output_base(url, _transcripts_dir(session_id))
    out = _write_transcript(base, fmt, transcript_txt, vtt_text)
    relpath = out.relative_to(_session_root(session_id)).as_posix()

    item = _add_item(
        session_id=session_id,
        kind="transcript",
        fmt=fmt,
        relpath=relpath,
        pinned=False,
        ttl_seconds=DEFAULT_TTL_SEC,
    )

    return {
        "id": item["id"],
        "session_id": session_id,
        "relpath": item["relpath"],
        "expires_at": item.get("expires_at"),
        "pinned": item.get("pinned", False),
        "format": item.get("format"),
        "size": item.get("size"),
        "kind": item.get("kind"),
        "created_at": item.get("created_at"),
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
    url: str,
    fmt: str = "txt",
    max_text_bytes: int | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    """
    Returns transcript text if small enough; otherwise writes to /data/<session_id>/transcripts and returns a manifest item object.
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

    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)

    base = _make_output_base(url, _transcripts_dir(session_id))
    out = _write_transcript(base, fmt, transcript_txt, vtt_text)
    relpath = out.relative_to(_session_root(session_id)).as_posix()

    item = _add_item(
        session_id=session_id,
        kind="transcript",
        fmt=fmt,
        relpath=relpath,
        pinned=False,
        ttl_seconds=DEFAULT_TTL_SEC,
    )

    return {
        "kind": "file",
        "id": item["id"],
        "session_id": session_id,
        "relpath": item["relpath"],
        "expires_at": item.get("expires_at"),
        "pinned": item.get("pinned", False),
        "format": item.get("format"),
        "size": item.get("size"),
        "created_at": item.get("created_at"),
        "bytes": text_bytes,
        "duration": duration,
        "duration_string": duration_string,
        "title": title,
        "is_live": is_live,
    }


@mcp.tool
def list_session_items(
    kind: str | None = None,
    format: str | None = None,
    pinned: bool | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    """
    Lists manifest items for the current session.
    Optional filters: kind, format, pinned.
    """
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    items = manifest.get("items", [])
    if kind:
        items = [i for i in items if i.get("kind") == kind]
    if format:
        items = [i for i in items if i.get("format") == format]
    if pinned is not None:
        items = [i for i in items if bool(i.get("pinned")) == pinned]
    return {"session_id": session_id, "items": items}


@mcp.tool
def pin_item(item_id: str, session_id: str | None = None, ctx: Any | None = None) -> dict:
    """
    Pins an item to prevent TTL cleanup.
    """
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id)
    if not item:
        raise ValueError("Item not found")
    item["pinned"] = True
    item["expires_at"] = None
    _save_manifest(session_id, manifest)
    return item


@mcp.tool
def unpin_item(item_id: str, session_id: str | None = None, ctx: Any | None = None) -> dict:
    """
    Unpins an item and re-applies default TTL.
    """
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id)
    if not item:
        raise ValueError("Item not found")
    item["pinned"] = False
    item["expires_at"] = _expires_at(DEFAULT_TTL_SEC)
    _save_manifest(session_id, manifest)
    return item


@mcp.tool
def set_item_ttl(item_id: str, ttl_seconds: int, session_id: str | None = None, ctx: Any | None = None) -> dict:
    """
    Sets TTL for an item (unpinned).
    """
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be >= 1")
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id)
    if not item:
        raise ValueError("Item not found")
    item["pinned"] = False
    item["expires_at"] = _expires_at(ttl_seconds)
    _save_manifest(session_id, manifest)
    return item


@mcp.tool
def delete_item(item_id: str, session_id: str | None = None, ctx: Any | None = None) -> dict:
    """
    Deletes a stored item and removes it from the manifest.
    """
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id)
    if not item:
        raise ValueError("Item not found")
    relpath = item.get("relpath", "")
    try:
        p = _resolve_relpath(session_id, relpath)
        if p.exists():
            p.unlink()
    except (OSError, ValueError):
        pass
    manifest["items"] = [i for i in manifest.get("items", []) if i.get("id") != item_id]
    _save_manifest(session_id, manifest)
    return {"deleted": True, "id": item_id}


@mcp.tool
def write_text_file(
    relpath: str,
    content: str,
    overwrite: bool = False,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    """
    Writes a derived text file under /data/<session_id>/derived and registers it in the manifest.
    """
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    if not relpath:
        raise ValueError("relpath is required")
    if relpath.startswith("/") or ".." in relpath.split("/"):
        raise ValueError("relpath must be a safe relative path")

    target = (_derived_dir(session_id) / relpath).resolve()
    if not _is_within_root(target, _derived_dir(session_id)):
        raise ValueError("relpath resolves outside derived directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise ValueError("File already exists; set overwrite=true to replace")

    target.write_text(content, encoding="utf-8")
    fmt = target.suffix.lstrip(".") or "txt"
    rel = target.relative_to(_session_root(session_id)).as_posix()

    item = _add_item(
        session_id=session_id,
        kind="derived",
        fmt=fmt,
        relpath=rel,
        pinned=False,
        ttl_seconds=DEFAULT_TTL_SEC,
    )
    return {
        "id": item["id"],
        "session_id": session_id,
        "relpath": item["relpath"],
        "expires_at": item.get("expires_at"),
        "pinned": item.get("pinned", False),
        "format": item.get("format"),
        "size": item.get("size"),
        "kind": item.get("kind"),
        "created_at": item.get("created_at"),
    }


@mcp.tool
def read_file_info(
    item_id: str | None = None,
    relpath: str | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    """
    Returns file size and normalized path for a session-scoped item.
    Provide either item_id or relpath.
    """
    if not item_id and not relpath:
        raise ValueError("Provide either item_id or relpath")

    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id, relpath=relpath)
    if item:
        p = _resolve_relpath(session_id, item.get("relpath", ""))
        size = p.stat().st_size
        item["size"] = size
        _save_manifest(session_id, manifest)

        return {
            "id": item.get("id"),
            "session_id": session_id,
            "path": str(p),
            "relpath": item.get("relpath"),
            "size": size,
            "pinned": bool(item.get("pinned")),
            "expires_at": item.get("expires_at"),
            "format": item.get("format"),
            "kind": item.get("kind"),
        }

    if relpath:
        p = _resolve_relpath(session_id, relpath)
        size = p.stat().st_size
        return {
            "id": None,
            "session_id": session_id,
            "path": str(p),
            "relpath": relpath,
            "size": size,
        }

    raise ValueError("Item not found")


@mcp.tool
def read_file_chunk(
    offset: int = 0,
    max_bytes: int = 200000,
    item_id: str | None = None,
    relpath: str | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    """
    Reads a chunk of a saved transcript file (for clients with output limits).
    Provide either item_id or relpath.
    Returns: { data, next_offset, eof, size, path, id }
    """
    if not item_id and not relpath:
        raise ValueError("Provide either item_id or relpath")

    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id, relpath=relpath)
    if item:
        p = _resolve_relpath(session_id, item.get("relpath", ""))
    elif relpath:
        p = _resolve_relpath(session_id, relpath)
    else:
        raise ValueError("Item not found")

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
        "id": item.get("id") if item else None,
    }


# ---------- MCP Resources & Templates ----------
def _encode_prompt_payload(
    name: str,
    item_id: str,
    session_id: str | None,
    prompt: str,
    extra_inputs: dict | None = None,
) -> str:
    inputs: dict = {"item_id": item_id}
    if session_id:
        inputs["session_id"] = session_id
    if extra_inputs:
        inputs.update(extra_inputs)

    sid_value = session_id or "YOUR_SESSION_ID"
    steps = [
        f"Call transcripts://session/{sid_value}/item/{item_id} to get metadata and inline content.",
        (
            "If content is missing or truncated, call "
            f"read_file_chunk(item_id=\"{item_id}\", session_id=\"{sid_value}\", "
            "offset=0, max_bytes=200000) until eof."
        ),
        "Complete the task and output only the result.",
        f"If you need this transcript later, call pin_item(item_id=\"{item_id}\").",
    ]

    payload = {
        "name": name,
        "inputs": inputs,
        "prompt": prompt,
        "recommended_steps": steps,
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.resource("transcripts://session/{session_id}/index")
def resource_session_index(session_id: str, ctx: Any | None = None) -> str:
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    return json.dumps(manifest, ensure_ascii=False)


@mcp.resource("transcripts://session/{session_id}/latest")
def resource_session_latest(session_id: str, ctx: Any | None = None) -> str:
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    manifest = _load_manifest(session_id)
    items = [i for i in manifest.get("items", []) if i.get("kind") == "transcript"]
    items.sort(key=_item_sort_key)
    latest = items[-1] if items else None
    return json.dumps({"session_id": session_id, "item": latest}, ensure_ascii=False)


@mcp.resource("transcripts://session/{session_id}/item/{item_id}")
def resource_session_item(session_id: str, item_id: str, ctx: Any | None = None) -> str:
    session_id = _get_session_id(session_id=session_id, ctx=ctx)
    _cleanup_session(session_id)
    item_id = urllib.parse.unquote(item_id)
    manifest = _load_manifest(session_id)
    item = _find_item(manifest, item_id=item_id)
    if not item:
        raise ValueError("Item not found")

    p = _resolve_relpath(session_id, item.get("relpath", ""))
    size = p.stat().st_size
    item["size"] = size
    _save_manifest(session_id, manifest)

    content = None
    truncated = False
    if size <= INLINE_TEXT_MAX_BYTES:
        content = p.read_text(encoding="utf-8", errors="replace")
    else:
        truncated = True

    payload = {
        "session_id": session_id,
        "item": item,
        "content": content,
        "truncated": truncated,
        "inline_max_bytes": INLINE_TEXT_MAX_BYTES,
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.resource("template://transcript/paragraphs/{item_id}")
def template_reflow(item_id: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Reformat the transcript into well-structured paragraphs. Preserve speaker turns if present, "
        "remove stutters/obvious filler where it improves readability, and keep the original meaning."
    )
    return _encode_prompt_payload("paragraphs", item_id, session_id, prompt)


@mcp.resource("template://transcript/summary/{item_id}")
def template_summary(item_id: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Summarize the transcript with:\n"
        "1) A one-paragraph executive summary.\n"
        "2) 5-8 bullet key points.\n"
        "Keep it concise and faithful to the source."
    )
    return _encode_prompt_payload("summary", item_id, session_id, prompt)


@mcp.resource("template://transcript/translate/{item_id}/{target_lang}")
def template_translate(item_id: str, target_lang: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    target_lang = urllib.parse.unquote(target_lang)
    prompt = (
        f"Translate the transcript to {target_lang}. Preserve proper nouns and technical terms. "
        "Keep formatting clean and readable."
    )
    return _encode_prompt_payload("translate", item_id, session_id, prompt, {"target_lang": target_lang})


@mcp.resource("template://transcript/outline/{item_id}")
def template_outline(item_id: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Create a structured outline or table of contents for the transcript. "
        "Use short section headings and group related content."
    )
    return _encode_prompt_payload("outline", item_id, session_id, prompt)


@mcp.resource("template://transcript/quotes/{item_id}")
def template_quotes(item_id: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Extract 5-10 quotable lines from the transcript. "
        "Each quote should be meaningful and stand alone."
    )
    return _encode_prompt_payload("quotes", item_id, session_id, prompt)


@mcp.resource("template://transcript/faq/{item_id}")
def template_faq(item_id: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "Create a concise FAQ based on the transcript content. Provide short Q/A pairs."
    return _encode_prompt_payload("faq", item_id, session_id, prompt)


@mcp.resource("template://transcript/glossary/{item_id}")
def template_glossary(item_id: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "Extract key terms and provide a short glossary (term + 1-2 sentence definition)."
    return _encode_prompt_payload("glossary", item_id, session_id, prompt)


@mcp.resource("template://transcript/action-items/{item_id}")
def template_action_items(item_id: str, ctx: Any | None = None) -> str:
    session_id = _extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "List action items or next steps implied by the transcript. Use clear, actionable phrasing."
    return _encode_prompt_payload("action_items", item_id, session_id, prompt)


# ---------- Run Server ----------
if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        path="/mcp",
        stateless_http=True,
    )
