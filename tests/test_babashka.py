import pytest
import asyncio
from examples.babashka.app import strip_ansi, BabashkaManager


def test_strip_ansi():
    """Verify that ANSI escape sequences are successfully removed."""
    assert strip_ansi("\x1b[31mhello\x1b[0m") == "hello"
    assert strip_ansi("plain text") == "plain text"
    assert strip_ansi("\x1b[1;32mGreen\x1b[0m text") == "Green text"


@pytest.mark.asyncio
async def test_babashka_manager_lifecycle():
    """Verify the startup, communication, and teardown lifecycle of BabashkaManager."""
    manager = BabashkaManager()

    # 1. Start the subprocess
    await manager.start()
    assert manager.process is not None
    assert len(manager.reader_tasks) == 2

    # Give a brief moment for the welcome message to be processed
    await asyncio.sleep(0.5)
    assert len(manager.output_buffer) > 0

    # 2. Write an evaluation code block
    await manager.write_input("(+ 10 20)")
    # Wait for the output to read from streams
    await asyncio.sleep(0.5)

    assert "(+ 10 20)" in manager.output_buffer
    assert "30" in manager.output_buffer

    # 3. Clear the shared buffer
    await manager.clear()
    assert manager.output_buffer == ""

    # 4. Reset the REPL session
    await manager.reset()
    await asyncio.sleep(0.5)
    assert "Reset" in manager.output_buffer

    # 5. Clean up subprocess and tasks to avoid test leaks
    if manager.process:
        try:
            manager.process.terminate()
            await manager.process.wait()
        except Exception:
            pass
    for t in manager.reader_tasks:
        t.cancel()
