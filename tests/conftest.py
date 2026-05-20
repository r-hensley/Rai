from pathlib import Path


def pytest_sessionstart(session):
    """Create a minimal repo-root .env for tests when missing.

    Bootstraps BOT_TOKEN, TRACEBACK_LOGGING_CHANNEL, BOT_TEST_CHANNEL,
    OWNER_ID, and GCSE_API so importing Rai during collection does not exit.
    """
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        return
    env_path.write_text(
        "BOT_TOKEN=test-token\n"
        "TRACEBACK_LOGGING_CHANNEL=1\n"
        "BOT_TEST_CHANNEL=1\n"
        "OWNER_ID=1\n"
        "GCSE_API=test-api-key\n",
        encoding="utf-8",
    )
