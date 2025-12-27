import logging

import logging_utils


def test_log_skips_when_level_disabled(caplog):
    with caplog.at_level(logging.ERROR, logger="yt_dlp_transcriber"):
        logging_utils._log(logging.DEBUG, "debug_event", detail="skip")
    assert not caplog.records


def test_log_emits_without_fields(caplog):
    with caplog.at_level(logging.INFO, logger="yt_dlp_transcriber"):
        logging_utils.log_info("info_event")
    assert any(record.message == "info_event" for record in caplog.records)


def test_log_skips_none_fields(caplog):
    with caplog.at_level(logging.INFO, logger="yt_dlp_transcriber"):
        logging_utils.log_info("info_event", skip=None, keep="ok")
    assert any("keep=ok" in record.message for record in caplog.records)
    assert all("skip=" not in record.message for record in caplog.records)


def test_log_includes_request_id_from_context(caplog):
    with caplog.at_level(logging.INFO, logger="yt_dlp_transcriber"):
        with logging_utils.request_context("req-123") as request_id:
            logging_utils.log_info("info_event")
    assert any(f"request_id={request_id}" in record.message for record in caplog.records)


def test_log_prefers_explicit_request_id(caplog):
    with caplog.at_level(logging.INFO, logger="yt_dlp_transcriber"):
        with logging_utils.request_context("req-ctx"):
            logging_utils.log_info("info_event", request_id="req-explicit")
    assert any("request_id=req-explicit" in record.message for record in caplog.records)
    assert all("request_id=req-ctx" not in record.message for record in caplog.records)
