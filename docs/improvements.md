# SOLID + OOP Improvements Plan

## Current State (Quick Analysis)
- `src/yt_dlp_transcriber/server.py` is a single module handling config, yt-dlp subprocesses, transcript parsing, storage/manifest IO, cleanup policy, FastMCP tool wiring, resources, and templates.
- Global state (`DATA_DIR`, limits, TTL, env config) is read at import time and shared across all tools.
- File/manifest operations are intertwined with MCP handlers, which makes unit testing rely on monkeypatching.
- Duplicate session preamble logic (`_get_session_id` + `_cleanup_session`) appears across tools.

## Goals (SOLID Focus)
- SRP: separate config, storage, transcription, and MCP wiring.
- OCP: add new transcript formats/providers without rewriting core services.
- LSP: depend on small interfaces that can be substituted in tests.
- ISP: split read/write concerns (metadata, read chunks, write outputs) into narrow interfaces.
- DIP: services depend on abstractions, not subprocess/filesystem implementations.

## Proposed Project Layout (flat `src/` root)
Top-level (conventional Python project shape):
- `pyproject.toml` (packaging/metadata/tooling; optional but recommended)
- `src/` (import root; run with `PYTHONPATH=src` or `python -m server`)
- `tests/` (pytest)
- `docs/`, `README.md`, `requirements*.txt`, `Dockerfile`, `Makefile`

Source layout (ports/adapters + application core under `src/`):
- `src/server.py` (composition root; wires config, services, MCP)
- `src/config.py` (AppConfig dataclass)
- `src/domain/`
  - `models.py` (Manifest, ManifestItem, enums)
  - `types.py` (SessionId, ItemId value objects)
  - `errors.py` (typed domain errors)
- `src/ports/` (interfaces/protocols)
  - `manifest_repo.py`
  - `transcriber.py`
  - `clock.py` (time provider for TTL logic)
- `src/services/`
  - `transcription_service.py` (use-case orchestration)
  - `session_service.py` (list/pin/unpin/ttl/delete/read)
- `src/adapters/`
  - `ytdlp_client.py` (subprocess adapter)
  - `filesystem_store.py` (path safety + IO)
  - `manifest_json_repo.py` (JSON-backed repository)
- `src/mcp/` (presentation layer)
  - `server.py` (FastMCP instance + registration)
  - `tools.py`
  - `resources.py`
  - `templates.py`

## Patterns to Apply
- Repository Pattern: `ManifestRepository` hides JSON IO and filtering.
- Strategy Pattern: `TranscriptWriter` for `txt/vtt/jsonl`, `TranscribeDecision` for auto text vs file.
- Factory: map format -> writer strategy.
- Adapter: `YtDlpClient` wraps subprocess so tests can swap a fake.
- Facade: `TranscriptionService` exposes a small API used by MCP tools.
- Value Objects: `SessionId` + `ItemId` validate once and pass typed values around.

## Step-by-Step Plan (No API Breaks)
Each step starts by updating tests to match the new structure before changing implementation.

1. **Config object**
   - Update tests to import `config.py` from `src/` and validate defaults/overrides.
   - Create `AppConfig` and load env values in one place.
   - Replace module-level globals with config instance passed into services.

2. **Domain models**
   - Update tests to use `domain/models.py` and `domain/types.py` imports.
   - Add dataclasses for `ManifestItem` and `Manifest`.
   - Use enums for `format` and `kind`.

3. **Storage layer**
   - Update tests to target `adapters/manifest_json_repo.py` and `adapters/filesystem_store.py`.
   - Introduce `SessionStore` for path resolution and safety checks.
   - Introduce `ManifestRepository` for CRUD + cleanup.
   - Add optional file locking for manifest updates.

4. **Transcription layer**
   - Update tests to target `adapters/ytdlp_client.py` and `services/transcription_service.py`.
   - Wrap yt-dlp calls in `YtDlpClient` (subprocess adapter).
   - Move VTT parsing to `TranscriptParser`.
   - Use `TranscriptWriter` strategies for output formats.

5. **Service layer**
   - Update tests to call service methods instead of MCP tool functions.
   - `TranscriptionService.transcribe_to_text/transcribe_to_file/transcribe_auto`.
   - `SessionService.list/pin/unpin/set_ttl/delete/read_info/read_chunk`.
   - Services accept `SessionId` and return `ManifestItem` models.

6. **MCP wiring**
   - Update tests that exercise MCP tools/resources to import from `src/mcp/*`.
   - Tools become thin adapters that resolve `session_id` then call services.
   - Resources/templates build payloads from service output only.

7. **Documentation refresh**
   - Update README, diagrams, and usage examples to match the new layout.
   - Update agent configuration snippets (Codex/Claude/etc.) and env var tables.
   - Verify docs reference the new entrypoints and import paths.

## Optional Enhancements
- Atomic manifest writes (write temp + rename) to prevent corruption.
- Caching for `youtube_get_duration` to avoid repeated metadata calls.
- Typed error hierarchy: `InvalidSessionId`, `NotFound`, `ExpiredItem`, `ExternalCommandError`.
- Structured logging with request/session ids.

## Suggested New Tests (Add only with approval)
- `tests/test_config.py`: env overrides, default TTL, max limits, default session id.
- `tests/test_domain_models.py`: enum values, dataclass validation, serialization helpers.
- `tests/test_manifest_repo.py`: add/find/update/remove, TTL cleanup, max size enforcement.
- `tests/test_filesystem_store.py`: path traversal protection, derived/transcripts dirs.
- `tests/test_transcription_service.py`: auto strategy chooses text vs file based on size.
- `tests/test_mcp_wiring.py`: tools call services, resources return consistent payloads.

## Definition of Done
- `server.py` becomes a thin composition root.
- Adding a new format (e.g., `md`) only touches writer strategy + enum.
- Unit tests no longer need to unwrap FastMCP tool decorators.
- Core services are isolated from FastMCP and subprocess details.

## Refactor Progress
- Step 1 (Config object): added `src/yt_dlp_transcriber/config.py` with `AppConfig`, updated `src/yt_dlp_transcriber/server.py` to use `APP_CONFIG`, and added `tests/test_config.py` with minimal fixture updates.
