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
- Test coverage is above 95%.
- All tests pass.
- Documentation is up to date.

## Refactor Progress
- Step 1 (Config object): added `src/yt_dlp_transcriber/config.py` with `AppConfig`, updated `src/yt_dlp_transcriber/server.py` to use `APP_CONFIG`, and added `tests/test_config.py` with minimal fixture updates.
- Step 2 (Domain models): added `src/yt_dlp_transcriber/domain/models.py` + `src/yt_dlp_transcriber/domain/types.py` with enums/value objects/dataclasses, plus `tests/test_domain_models.py`.
- Step 3 (Storage layer): added `src/yt_dlp_transcriber/adapters/filesystem_store.py` + `src/yt_dlp_transcriber/adapters/manifest_json_repo.py` with tests in `tests/test_filesystem_store.py` and `tests/test_manifest_repo.py`.
- Step 4 (Transcription layer): added `src/yt_dlp_transcriber/adapters/ytdlp_client.py` and `src/yt_dlp_transcriber/services/transcription_service.py` with tests in `tests/test_ytdlp_client.py` and `tests/test_transcription_service.py`.
- Step 5 (Service layer): added `src/yt_dlp_transcriber/services/session_service.py`, updated `src/yt_dlp_transcriber/services/transcription_service.py`, and aligned tests in `tests/test_manifest.py`, `tests/test_resources.py`, and `tests/test_transcription_service.py`.
- Step 6 (MCP wiring): added `src/yt_dlp_transcriber/mcp/` modules (app/tools/resources/templates/deps/session), rewired `src/yt_dlp_transcriber/server.py`, and aligned MCP-related tests.
- Tests: removed unused `tests/conftest.py` fixture that imported the FastMCP server, so unit tests no longer require `fastmcp` at import time.
- Tests: added a lightweight `FastMCP` stub fallback in `src/yt_dlp_transcriber/mcp/app.py` so importing MCP modules works without `fastmcp` installed.
- Tests: added `pytest.ini` with `pythonpath = src` so `pytest` works without manually exporting `PYTHONPATH`.
- MCP: registered resources/templates via explicit `mcp.resource(...)(func)` calls to keep the exported functions callable even when FastMCP returns template objects.
- Step 7 (Documentation refresh): updated `README.md` testing instructions and repository layout to match the new module structure.
- Optional enhancement: `ManifestRepository.save` now writes via temp file + `os.replace` (tested in `tests/test_manifest_repo.py`) to make manifest writes atomic.
- Optional enhancement (errors): added `src/yt_dlp_transcriber/domain/errors.py`, wired typed errors through ids, services, resources, and yt-dlp adapter, with tests in `tests/test_errors.py` and `tests/test_ytdlp_client.py`.
- Optional enhancement (caching): added `YTDLP_INFO_CACHE_TTL_SEC` config and in-memory caching in `src/yt_dlp_transcriber/adapters/ytdlp_client.py`, with tests in `tests/test_ytdlp_client.py` and `tests/test_config.py`.
- Ports: added `src/yt_dlp_transcriber/ports/` protocols and updated services to depend on ports for manifest repositories and transcribers.
- Clock port: added `src/yt_dlp_transcriber/ports/clock.py` and wired `ManifestRepository` to use an injected clock for timestamps, with tests in `tests/test_manifest_repo.py`.
- Logging: added lightweight structured logging helper and log events across debug/info/warning/error in MCP tools/resources and yt-dlp adapter.
- MCP error mapping: added `src/yt_dlp_transcriber/mcp/error_handling.py` and wired tools/resources/templates to map typed errors to user-friendly exceptions, with tests in `tests/test_mcp_error_mapping.py`.
- Documentation: updated README examples to note yt-dlp metadata caching and added logging guidance.
- MCP errors: added explicit error codes (`ERR_INVALID_SESSION`, `ERR_INVALID_ITEM`, `ERR_NOT_FOUND`, `ERR_EXPIRED_ITEM`, `ERR_EXTERNAL_COMMAND`) in mapped exceptions and documented them in README.
- Documentation: added coverage commands to README and added `coverage` to dev requirements.
- Coverage: added tests for MCP session/templates/resources helpers, FastMCP fallback import, logging helper branches, config env defaults, filesystem symlink safety, and service builder defaults.
- Coverage: added manifest repository and session service tests for error branches, cleanup edge cases, lock handling, and input validation.
- Coverage: added yt-dlp client and transcription service tests for subtitle failures, parsing edge cases, writer outputs, and auto-transcribe validation.
- Coverage: refined new tests around cleanup limits, session header extraction, and writer mapping to keep coverage suites green.
- Refactor: centralized session/item id coercion helpers in `domain/types.py` and reused them in store, repo, and session service.
- Coverage: added tests for enum list filtering, cleanup removal error handling, TTL updates, delete edge cases, symlink escapes, and missing file errors.
- Coverage: expanded tests for logging field filtering and expired-item mapping; manifest repo cleanup/remove error paths and lock fallback now covered (overall coverage ~98%).
- Refactor (tests): added time parsing tests and updated resource/manifest tests to use shared time parsing helper.
- Refactor: added `domain/time_utils.py` and replaced duplicated timestamp parsing in manifest repo and MCP resources.
- Tests: added coverage for new MCP payload helper to lock in prompt payload structure.
- Refactor: centralized MCP JSON payload encoding and prompt payload construction in `mcp/payloads.py`.
