# Scripts

Utility scripts for OpenAPI schema generation, load testing, and SDK usage examples.

## OpenAPI Schema Generation

- **`generate-openapi.py`**:
    Feature-rich script to generate and validate OpenAPI schemas from the FastAPI application.

    **Commands:**

    - **Generate** - Create OpenAPI schema from FastAPI app:
        ```shell
        uv run ./scripts/generate-openapi.py generate --output-spec=openapi.json
        ```

    - **Generate and Diff** - Generate schema and compare with existing spec:
        ```shell
        uv run ./scripts/generate-openapi.py generate-and-diff \
            --existing-spec ./openapi.json \
            --output-spec ./openapi.json \
            --fail-on-diff
        ```

    Used in pre-commit hooks to ensure the OpenAPI schema stays synchronized with code changes.

- **`generate-openapi-simple.py`**

    Simplified version demonstrating the core OpenAPI generation logic. Generates schema and compares it with the existing `openapi.json` file, exiting with an error if they differ. Useful for understanding the basics before working with the full-featured `generate-openapi.py`.

    **Usage:**
    ```shell
    uv run ./scripts/generate-openapi-simple.py
    ```

## Load Testing

**`locustfile.py`**

Locust configuration for load testing the Files API. Simulates realistic user flows including file uploads, downloads, deletions, and AI file generation.

**Tasks:**
- `file_operations_flow`: Tests basic CRUD operations (list, upload, describe, download, delete)
- `generate_ai_files_flow`: Tests AI-powered file generation (text, image, audio)

**Usage:**
```shell
# Start with docker-compose
./run run-locust

# Or run Locust directly
uv run locust -f scripts/locustfile.py --host=http://localhost:8000
```

Access the Locust web UI at http://localhost:8089 to configure and monitor load tests.

## SDK Testing

**`try_client.py`**

Example script demonstrating usage of the auto-generated Python SDK (`files-api-sdk`). Shows how to upload files using the client library.

**Usage:**
```shell
# First, generate and install the SDK
./run generate-client-library
./run install-generated-sdk

# Then run the example
uv run ./scripts/try_client.py
```

Make sure the API is running locally before executing this script.
