from pathlib import Path


def pytest_sessionstart(session):
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        return
    env_path.write_text(
        "BOT_TOKEN=test-token\n"
        "TRACEBACK_LOGGING_CHANNEL=1\n"
        "BOT_TEST_CHANNEL=1\n"
        "OWNER_ID=1\n"
        "GCSE_API=\n",
        encoding="utf-8",
    )
