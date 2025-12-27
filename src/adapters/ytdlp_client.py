from __future__ import annotations

import json
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from config import AppConfig
from domain.errors import ExternalCommandError
from logging_utils import log_debug, log_error, log_warning


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
        cache_ttl_sec: int = 0,
        time_provider: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._runner = runner or subprocess.run
        self._temp_dir_factory = temp_dir_factory or _temp_dir
        self._cache_ttl_sec = cache_ttl_sec
        self._time_provider = time_provider or time.time
        self._info_cache: dict[str, tuple[float, dict]] = {}

    def get_info(self, url: str) -> dict:
        if self._cache_ttl_sec > 0:
            cached = self._info_cache.get(url)
            if cached:
                ts, payload = cached
                if self._time_provider() - ts <= self._cache_ttl_sec:
                    log_debug("ytdlp_info_cache_hit", url=url)
                    return payload

        log_debug("ytdlp_info_fetch", url=url)
        cmd = _build_info_command(self._config, url)
        proc = self._runner(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=self._config.timeout_sec,
        )

        if proc.returncode != 0:
            log_error("ytdlp_info_failed", url=url, code=proc.returncode)
            raise ExternalCommandError(
                f"yt-dlp metadata failed (code {proc.returncode}). Output:\n{proc.stdout}"
            )

        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        json_line = None
        for line in reversed(lines):
            if line.lstrip().startswith("{") and line.rstrip().endswith("}"):
                json_line = line
                break

        if json_line is None:
            log_error("ytdlp_info_missing_json", url=url)
            raise ExternalCommandError(f"yt-dlp metadata output missing JSON. Output:\n{proc.stdout}")

        try:
            payload = json.loads(json_line)
        except json.JSONDecodeError as exc:
            log_error("ytdlp_info_parse_failed", url=url)
            raise ExternalCommandError(f"Failed to parse yt-dlp metadata JSON: {exc}") from exc

        if self._cache_ttl_sec > 0:
            self._info_cache[url] = (self._time_provider(), payload)
            log_debug("ytdlp_info_cache_store", url=url, ttl=self._cache_ttl_sec)

        return payload

    def get_subtitles(self, url: str) -> YtDlpSubtitles:
        with self._temp_dir_factory("yt_transcribe_") as workdir:
            log_debug("ytdlp_subtitles_fetch", url=url, dir=str(workdir))
            cmd = _build_subs_command(self._config, url, workdir)
            proc = self._runner(
                cmd,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self._config.timeout_sec,
            )

            vtts = sorted(workdir.glob("*.en.vtt"))
            if not vtts:
                vtts = sorted(workdir.glob("*.vtt"))

            if proc.returncode != 0:
                if not vtts:
                    log_error("ytdlp_subtitles_failed", url=url, code=proc.returncode)
                    raise ExternalCommandError(
                        f"yt-dlp failed (code {proc.returncode}). Output:\n{proc.stdout}"
                    )
                log_warning("ytdlp_subtitles_partial_success", url=url, code=proc.returncode)

            if not vtts:
                log_error("ytdlp_subtitles_missing", url=url)
                raise ExternalCommandError(f"No subtitle files were produced. yt-dlp output:\n{proc.stdout}")

            vtt_path = vtts[-1]
            log_debug("ytdlp_subtitles_selected", url=url, file=vtt_path.name)
            vtt_text = vtt_path.read_text(encoding="utf-8", errors="replace")
            return YtDlpSubtitles(vtt_text=vtt_text, stdout=proc.stdout, picked_file=vtt_path.name)
