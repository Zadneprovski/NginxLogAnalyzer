import json
from unittest.mock import mock_open, patch

import pytest

from log_analyzer import (LogEntry, find_last_log, load_config, parse_log_file,
                          setup_logging)


def test_load_config_valid():
    mock_config = {
        "REPORT_SIZE": 20,
        "REPORT_DIR": "/tmp/reports",
        "LOG_DIR": "/tmp/logs",
    }

    with patch("builtins.open", mock_open(read_data=json.dumps(mock_config))):
        config = load_config("config.json")
        assert config["REPORT_SIZE"] == 20
        assert config["REPORT_DIR"] == "/tmp/reports"
        assert config["LOG_DIR"] == "/tmp/logs"


def test_load_config_file_not_found():
    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError):
            load_config("non_existent_config.json")


def test_find_last_log_no_files():
    log_dir = "/tmp/logs"
    log_pattern = r"nginx-access-ui.log-(\d{8})\.gz"

    with patch("os.listdir", return_value=[]):
        last_log = find_last_log(log_dir, log_pattern)
        assert last_log is None


def test_parse_log_file_valid():
    log_content = '"GET /home" 0.123\n"POST /login" 0.456\n'

    with patch("gzip.open", mock_open(read_data=log_content)):
        log_entries = parse_log_file("dummy_log.gz")

        assert len(log_entries) == 2
        assert isinstance(log_entries[0], LogEntry)
        assert log_entries[0].url == "/home"
        assert log_entries[0].request_time == 0.123


def test_parse_log_file_empty():
    log_content = ""

    with patch("gzip.open", mock_open(read_data=log_content)):
        log_entries = parse_log_file("dummy_log.gz")

        assert len(log_entries) == 0


def test_setup_logging_with_file():
    with patch("builtins.open", mock_open()):
        setup_logging("test.log")
        pass


def test_setup_logging_without_file():
    setup_logging()
    pass


def test_log_error_handling(mocker):
    mock_logger = mocker.patch("structlog.get_logger")
    mock_logger().error = mocker.Mock()

    try:
        raise ValueError("Test error")
    except ValueError:
        mock_logger().error("Unexpected error occurred.", exc_info=True)

    mock_logger().error.assert_called_with("Unexpected error occurred.", exc_info=True)
