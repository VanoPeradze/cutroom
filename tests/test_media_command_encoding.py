"""Media commands emit UTF-8 metadata even on Windows with a legacy locale."""
import sys

import pytest

from cutroom.media import run_command


@pytest.mark.parametrize("cancellable", [False, True])
def test_media_command_preserves_utf8_text_and_replaces_invalid_diagnostics(cancellable):
    child = "import os; os.write(1, '\u05e9\u05dc\u05d5\u05dd'.encode('utf-8')); os.write(2, b'\\xff')"
    kwargs = {"cancel_check": lambda: None} if cancellable else {}
    result = run_command([sys.executable, "-c", child], timeout=5, **kwargs)
    assert result.stdout == "\u05e9\u05dc\u05d5\u05dd"
    assert result.stderr == "\ufffd"


@pytest.mark.parametrize("cancellable", [False, True])
def test_binary_media_command_retains_exact_pcm_bytes(cancellable):
    child = "import os; os.write(1, b'\\x00\\xff\\x80\\xd7'); os.write(2, b'\\xfe')"
    kwargs = {"cancel_check": lambda: None} if cancellable else {}
    result = run_command([sys.executable, "-c", child], text=False, timeout=5, **kwargs)
    assert result.stdout == b"\x00\xff\x80\xd7"
    assert result.stderr == b"\xfe"
