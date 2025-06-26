import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator

import pytest
import requests  # type: ignore

THIS_DIR = Path(__file__).parent
MOCKED_OPENAI_SERVER_PY_PATH = THIS_DIR / "../mocks/openai_fastapi_mock_app.py"
OPENAI_MOCK_PORT: int = 1080
OPENAI_BASE_URL: str = f"http://localhost:{OPENAI_MOCK_PORT}"
OPENAI_API_KEY: str = "mocked_openai_api_key"


@pytest.fixture(scope="session")
def mocked_openai() -> Generator[None, Any, None]:
    """Start a mocked OpenAI server running on port 5005 for testing calls to OpenAI."""
    openai_mock_process = start_mock_server(port=OPENAI_MOCK_PORT)

    with temporary_env_vars(
        {
            "OPENAI_BASE_URL": OPENAI_BASE_URL,
            "OPENAI_API_KEY": OPENAI_API_KEY,
        }
    ):
        yield

    # Cleanup: Terminate the OpenAI mock server process
    openai_mock_process.terminate()
    openai_mock_process.wait()


#################
# --- Utils --- #
#################


@contextmanager
def temporary_env_vars(env_vars: Dict[str, str]) -> Generator[None, Any, None]:
    """Temporarily set and restore environment variables."""
    original_env_vars = os.environ.copy()
    os.environ.update(env_vars)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original_env_vars)


def _stream_output(pipe, name):
    """Stream output from a subprocess pipe."""
    for line in iter(pipe.readline, ""):
        if line:
            print(f"[{name}] {line.strip()}")


def start_mock_server(port: int, max_retries: int = 3, retry_delay_seconds: int = 1) -> subprocess.Popen:
    """Start a mock server and verify it's running by hitting the `/` endpoint."""
    # pylint: disable=consider-using-with
    process = subprocess.Popen(
        [
            # launch the mocked server using python interpreter from the same virtual env used for running the tests
            sys.executable,
            # the mocked server is a python file in the mocks directory
            str(MOCKED_OPENAI_SERVER_PY_PATH),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env={"OPENAI_MOCK_PORT": str(port)},
    )

    # Start threads to asynchronously print stdout and stderr
    stdout_thread = threading.Thread(target=_stream_output, args=(process.stdout, "stdout"))
    stderr_thread = threading.Thread(target=_stream_output, args=(process.stderr, "stderr"))
    stdout_thread.start()
    stderr_thread.start()

    for _ in range(max_retries):
        try:
            response = requests.get(f"http://localhost:{port}/")
            if response.status_code == 200:
                return process
        except requests.exceptions.ConnectionError:
            time.sleep(retry_delay_seconds)

    process.terminate()
    stdout_thread.join()
    stderr_thread.join()
    raise RuntimeError(f"Mock server at port {port} failed to start after {max_retries} attempts.")
