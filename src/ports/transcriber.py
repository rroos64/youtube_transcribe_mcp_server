from __future__ import annotations

from typing import Protocol


class SubtitleSource(Protocol):
    vtt_text: str
    stdout: str
    picked_file: str


class TranscriberPort(Protocol):
    def get_info(self, url: str) -> dict:
        ...

    def get_subtitles(self, url: str) -> SubtitleSource:
        ...
