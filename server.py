import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastmcp import FastMCP

# FastMCP v2.14.x uses `stateless_http` (not `stateless`)
mcp = FastMCP(
    "yt-dlp-transcriber",
    instructions=(
        "Fetches YouTube subtitles via yt-dlp and returns cleaned transcripts. "
        "Use youtube_transcribe_auto to choose text vs file output, or youtube_transcribe_to_file "
        "for large outputs and read_file_chunk/read_file_info to page."
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

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_YT_URL_RE = re.compile(r"^https?://(www\.)?youtube\.com/watch\?v=|^https?://youtu\.be/")

# ---------- Helpers ----------
def _is_youtube_url(url: str) -> bool:
    return bool(_YT_URL_RE.search(url))


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


def _make_output_base(url: str) -> Path:
    vid_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return DATA_DIR / f"youtube_{vid_hash}_{stamp}"


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
def youtube_transcribe_to_file(url: str, fmt: str = "txt") -> str:
    """
    Saves transcript to /data (bind-mount this to host) and returns the saved filepath.
    fmt: "txt" | "vtt" | "jsonl"
    """
    if not _is_youtube_url(url):
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")
    if fmt not in ("txt", "vtt", "jsonl"):
        raise ValueError("fmt must be one of: txt, vtt, jsonl")

    res = _run_ytdlp_subs(url)
    vtt_text = res["vtt_text"]
    transcript_txt = _vtt_to_text(vtt_text)

    base = _make_output_base(url)
    out = _write_transcript(base, fmt, transcript_txt, vtt_text)
    return str(out)


@mcp.tool
def youtube_transcribe_auto(url: str, fmt: str = "txt", max_text_bytes: int | None = None) -> dict:
    """
    Returns transcript text if small enough; otherwise writes to /data and returns file info.
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

    res = _run_ytdlp_subs(url)
    vtt_text = res["vtt_text"]
    transcript_txt = _vtt_to_text(vtt_text)

    if not transcript_txt:
        raise RuntimeError(f"Subtitle file was empty after parsing ({res['picked_file']}).")

    text_bytes = len(transcript_txt.encode("utf-8"))
    if text_bytes <= max_text_bytes:
        return {"kind": "text", "text": transcript_txt, "bytes": text_bytes}

    base = _make_output_base(url)
    out = _write_transcript(base, fmt, transcript_txt, vtt_text)
    return {"kind": "file", "path": str(out), "bytes": text_bytes, "fmt": fmt}


@mcp.tool
def read_file_info(path: str) -> dict:
    """
    Returns file size and normalized path.
    """
    p = Path(path)
    if not p.is_absolute():
        p = (DATA_DIR / p).resolve()

    if not p.exists():
        raise ValueError(f"File does not exist: {p}")

    return {"path": str(p), "size": p.stat().st_size}


@mcp.tool
def read_file_chunk(path: str, offset: int = 0, max_bytes: int = 200000) -> dict:
    """
    Reads a chunk of a saved transcript file (for clients with output limits).
    Returns: { data, next_offset, eof, size, path }
    """
    p = Path(path)
    if not p.is_absolute():
        p = (DATA_DIR / p).resolve()

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
