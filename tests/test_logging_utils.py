import logging

from yt_dlp_transcriber import logging_utils


def test_log_skips_when_level_disabled(caplog):
    with caplog.at_level(logging.ERROR, logger="yt_dlp_transcriber"):
        logging_utils._log(logging.DEBUG, "debug_event", detail="skip")
    assert not caplog.records


def test_log_emits_without_fields(caplog):
    with caplog.at_level(logging.INFO, logger="yt_dlp_transcriber"):
        logging_utils.log_info("info_event")
    assert any(record.message == "info_event" for record in caplog.records)
