import os
import subprocess
from typing import Generator

import pytest
from tests.consts import PROJECT_DIR


def point_away_from_openai() -> None:
    """Set the environment variables to point away from OpenAI for testing."""
    os.environ["OPENAI_BASE_URL"] = "http://localhost:1080"
    os.environ["OPENAI_API_KEY"] = "mocked_key"


def unset_openai_environment_variables() -> None:
    """Unset the environment variables set for testing."""
    os.environ.pop("OPENAI_BASE_URL", None)
    os.environ.pop("OPENAI_API_KEY", None)


@pytest.fixture(scope="session")
def mocked_openai() -> Generator[None, None, None]:
    """Set up a mocked OpenAI environment for testing."""
    # Set the environment variables to point away from OpenAI
    point_away_from_openai()

    # Path to the Docker Compose file
    # compose_file_path = Path(__file__).parent / "../../mock-openai-docker-compose.yaml"
    compose_file_path = PROJECT_DIR / "mock-openai-docker-compose.yaml"

    # Start the Docker Compose to mock the OpenAI API
    subprocess.run(
        ["docker", "compose", "--file", str(compose_file_path), "up", "--detach"],
        check=True,
    )

    yield

    # Clean up
    subprocess.run(["docker", "compose", "--file", str(compose_file_path), "down"], check=True)

    # Unset the environment variables
    unset_openai_environment_variables()
