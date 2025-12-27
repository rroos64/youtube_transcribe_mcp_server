from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Protocol

from adapters.filesystem_store import SessionStore
from ports.manifest_repo import ManifestRepositoryPort
from ports.transcriber import TranscriberPort
from domain.models import ItemKind, ManifestItem, TranscriptFormat
from domain.types import SessionId


class TranscriptParser:
    def vtt_to_lines(self, vtt: str) -> list[str]:
        out_lines: list[str] = []
        for raw in vtt.splitlines():
            line = raw.strip()
            if not line:
                continue

            if line.startswith(("WEBVTT", "NOTE", "STYLE", "REGION", "Kind:", "Language:")):
                continue

            if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s-->\s", line):
                continue

            line = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", "", line)
            line = re.sub(r"</?c(\.[^>]*)?>", "", line)
            line = re.sub(r"</?[^>]+>", "", line)
            line = re.sub(r"\s+", " ", line).strip()

            if line:
                out_lines.append(line)

        return out_lines

    def dedupe_lines(self, lines: list[str], window: int = 6) -> list[str]:
        deduped: list[str] = []
        recent: list[str] = []
        prev: str | None = None

        for line in lines:
            if line == prev:
                continue
            if line in recent:
                continue
            deduped.append(line)
            recent.append(line)
            if len(recent) > window:
                recent = recent[-window:]
            prev = line

        return deduped

    def vtt_to_text(self, vtt: str) -> str:
        lines = self.vtt_to_lines(vtt)
        lines = self.dedupe_lines(lines, window=6)
        return "\n".join(lines).strip()


class TranscriptWriter(Protocol):
    def write(self, base: Path, transcript_text: str, vtt_text: str) -> Path:
        ...


class TxtWriter:
    def write(self, base: Path, transcript_text: str, vtt_text: str) -> Path:
        out = base.with_suffix(".txt")
        out.write_text(transcript_text + "\n", encoding="utf-8")
        return out


class VttWriter:
    def write(self, base: Path, transcript_text: str, vtt_text: str) -> Path:
        out = base.with_suffix(".vtt")
        out.write_text(vtt_text, encoding="utf-8")
        return out


class JsonlWriter:
    def write(self, base: Path, transcript_text: str, vtt_text: str) -> Path:
        out = base.with_suffix(".jsonl")
        with out.open("w", encoding="utf-8") as handle:
            for line in transcript_text.splitlines():
                handle.write(json.dumps({"text": line}, ensure_ascii=False) + "\n")
        return out


def default_writers() -> Mapping[TranscriptFormat, TranscriptWriter]:
    return {
        TranscriptFormat.TXT: TxtWriter(),
        TranscriptFormat.VTT: VttWriter(),
        TranscriptFormat.JSONL: JsonlWriter(),
    }


@dataclass(frozen=True)
class VideoInfo:
    duration: int | None
    duration_string: str | None
    title: str | None
    is_live: bool | None


@dataclass(frozen=True)
class TranscriptionResult:
    kind: str
    text: str | None
    item: ManifestItem | None
    bytes: int
    info: VideoInfo


def _build_info(payload: dict) -> VideoInfo:
    return VideoInfo(
        duration=payload.get("duration"),
        duration_string=payload.get("duration_string"),
        title=payload.get("title"),
        is_live=payload.get("is_live"),
    )


class TranscriptionService:
    def __init__(
        self,
        client: TranscriberPort,
        parser: TranscriptParser,
        store: SessionStore,
        repo: ManifestRepositoryPort,
        writers: Mapping[TranscriptFormat, TranscriptWriter] | None = None,
    ) -> None:
        self._client = client
        self._parser = parser
        self._store = store
        self._repo = repo
        self._writers = writers or default_writers()

    def transcribe_to_text(self, url: str) -> str:
        subs = self._client.get_subtitles(url)
        transcript = self._parser.vtt_to_text(subs.vtt_text)
        if not transcript:
            raise RuntimeError(f"Subtitle file was empty after parsing ({subs.picked_file}).")
        return transcript

    def transcribe_to_file(
        self,
        *,
        url: str,
        fmt: TranscriptFormat,
        session_id: SessionId | str,
    ) -> ManifestItem:
        subs = self._client.get_subtitles(url)
        transcript = self._parser.vtt_to_text(subs.vtt_text)
        if not transcript:
            raise RuntimeError(f"Subtitle file was empty after parsing ({subs.picked_file}).")

        return self._write_transcript(
            url=url,
            fmt=fmt,
            session_id=session_id,
            transcript=transcript,
            vtt_text=subs.vtt_text,
        )

    def transcribe_auto(
        self,
        *,
        url: str,
        fmt: TranscriptFormat,
        max_text_bytes: int,
        session_id: SessionId | str | None,
    ) -> TranscriptionResult:
        if max_text_bytes < 1:
            raise ValueError("max_text_bytes must be >= 1")

        info = self._client.get_info(url)
        subs = self._client.get_subtitles(url)
        transcript = self._parser.vtt_to_text(subs.vtt_text)
        if not transcript:
            raise RuntimeError(f"Subtitle file was empty after parsing ({subs.picked_file}).")

        size = len(transcript.encode("utf-8"))
        info_obj = _build_info(info)
        if size <= max_text_bytes:
            return TranscriptionResult(
                kind="text",
                text=transcript,
                item=None,
                bytes=size,
                info=info_obj,
            )

        if session_id is None:
            raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

        item = self._write_transcript(
            url=url,
            fmt=fmt,
            session_id=session_id,
            transcript=transcript,
            vtt_text=subs.vtt_text,
        )
        return TranscriptionResult(
            kind="file",
            text=None,
            item=item,
            bytes=size,
            info=info_obj,
        )

    def _write_transcript(
        self,
        *,
        url: str,
        fmt: TranscriptFormat,
        session_id: SessionId | str,
        transcript: str,
        vtt_text: str,
    ) -> ManifestItem:
        base = self._make_output_base(url, self._store.transcripts_dir(session_id))
        writer = self._writers.get(fmt)
        if writer is None:
            raise ValueError("fmt must be one of: txt, vtt, jsonl")
        out = writer.write(base, transcript, vtt_text)
        relpath = out.relative_to(self._store.session_root(session_id)).as_posix()
        return self._repo.add_item(
            session_id=session_id,
            kind=ItemKind.TRANSCRIPT,
            fmt=fmt,
            relpath=relpath,
            pinned=False,
            ttl_seconds=self._repo.default_ttl_sec,
        )

    @staticmethod
    def _make_output_base(url: str, base_dir: Path) -> Path:
        vid_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        return base_dir / f"youtube_{vid_hash}_{stamp}"
