from __future__ import annotations

import json
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from yt_dlp_transcriber.config import AppConfig


@dataclass(frozen=True)
class YtDlpSubtitles:
    vtt_text: str
    stdout: str
    picked_file: str


def _build_info_command(config: AppConfig, url: str) -> list[str]:
    return [
        config.ytdlp_bin,
        "--remote-components",
        config.remote_ejs,
        "--extractor-args",
        f"youtube:player_client={config.player_client}",
        "--skip-download",
        "--no-progress",
        "--no-playlist",
        "--dump-json",
        url,
    ]


def _build_subs_command(config: AppConfig, url: str, workdir: Path) -> list[str]:
    return [
        config.ytdlp_bin,
        "--remote-components",
        config.remote_ejs,
        "--extractor-args",
        f"youtube:player_client={config.player_client}",
        "--write-auto-subs",
        "--sub-lang",
        config.sub_lang,
        "--skip-download",
        "--no-progress",
        "--paths",
        str(workdir),
        url,
    ]


@contextmanager
def _temp_dir(prefix: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix=prefix) as td:
        yield Path(td)


class YtDlpClient:
    def __init__(
        self,
        config: AppConfig,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        temp_dir_factory: Callable[[str], Iterator[Path]] | None = None,
    ) -> None:
        self._config = config
        self._runner = runner or subprocess.run
        self._temp_dir_factory = temp_dir_factory or _temp_dir

    def get_info(self, url: str) -> dict:
        cmd = _build_info_command(self._config, url)
        proc = self._runner(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=self._config.timeout_sec,
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

    def get_subtitles(self, url: str) -> YtDlpSubtitles:
        with self._temp_dir_factory("yt_transcribe_") as workdir:
            cmd = _build_subs_command(self._config, url, workdir)
            proc = self._runner(
                cmd,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self._config.timeout_sec,
            )

            if proc.returncode != 0:
                raise RuntimeError(f"yt-dlp failed (code {proc.returncode}). Output:\n{proc.stdout}")

            vtts = sorted(workdir.glob("*.en.vtt"))
            if not vtts:
                vtts = sorted(workdir.glob("*.vtt"))
            if not vtts:
                raise RuntimeError(f"No subtitle files were produced. yt-dlp output:\n{proc.stdout}")

            vtt_path = vtts[-1]
            vtt_text = vtt_path.read_text(encoding="utf-8", errors="replace")
            return YtDlpSubtitles(vtt_text=vtt_text, stdout=proc.stdout, picked_file=vtt_path.name)
