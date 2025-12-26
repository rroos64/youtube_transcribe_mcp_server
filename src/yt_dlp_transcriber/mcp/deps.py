from __future__ import annotations

from dataclasses import dataclass

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.adapters.ytdlp_client import YtDlpClient
from yt_dlp_transcriber.config import AppConfig
from yt_dlp_transcriber.services.session_service import SessionService
from yt_dlp_transcriber.services.transcription_service import TranscriptParser, TranscriptionService


@dataclass(frozen=True)
class Services:
    config: AppConfig
    store: SessionStore
    manifest_repo: ManifestRepository
    ytdlp_client: YtDlpClient
    transcription_service: TranscriptionService
    session_service: SessionService


_services: Services | None = None


def build_services(config: AppConfig | None = None) -> Services:
    if config is None:
        config = AppConfig.from_env()
    store = SessionStore(config.data_dir)
    repo = ManifestRepository(
        store,
        default_ttl_sec=config.default_ttl_sec,
        max_session_items=config.max_session_items,
        max_session_bytes=config.max_session_bytes,
    )
    client = YtDlpClient(config, cache_ttl_sec=config.info_cache_ttl_sec)
    parser = TranscriptParser()
    transcription_service = TranscriptionService(client, parser, store, repo)
    session_service = SessionService(store, repo)
    return Services(
        config=config,
        store=store,
        manifest_repo=repo,
        ytdlp_client=client,
        transcription_service=transcription_service,
        session_service=session_service,
    )


def get_services() -> Services:
    global _services
    if _services is None:
        _services = build_services()
    return _services


def set_services(services: Services | None) -> None:
    global _services
    _services = services
