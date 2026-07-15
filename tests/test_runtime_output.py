"""Background runtime output tests."""

import logging
import warnings

from martin.utils.logger import AppLogger
from martin.utils.runtime_output import capture_runtime_output


def test_runtime_output_capture_redirects_stdout_stderr_and_warnings(
    tmp_path, monkeypatch
):
    log_path = tmp_path / "runtime.log"
    monkeypatch.setattr(
        "martin.utils.runtime_output.get_runtime_log_path",
        lambda: log_path,
    )

    with capture_runtime_output():
        print("model progress")
        warnings.warn("library warning", FutureWarning)

    content = log_path.read_text(encoding="utf-8")
    assert "model progress" in content
    assert "library warning" in content


def test_disable_console_output_preserves_file_handler(tmp_path):
    logger = AppLogger("background-only-test", log_dir=str(tmp_path)).get_logger()

    try:
        AppLogger.disable_console_output()

        assert any(isinstance(handler, logging.FileHandler) for handler in logger.handlers)
        assert not any(
            isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
            for handler in logger.handlers
        )
    finally:
        AppLogger._console_enabled = True
