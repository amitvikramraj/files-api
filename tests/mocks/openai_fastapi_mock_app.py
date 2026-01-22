"""
Define a FastAPI app emulates two of OpenAI's text and image generation endpoints.

No matter the prompt, it always returns the same text or image.

Access the server at `http://localhost:1080`.
"""

import os
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
)

MOCK_PORT = int(os.getenv("OPENAI_MOCK_PORT", "1080"))  # Configurable port variable

THIS_DIR = Path(__file__).parent
SAMPLE_TTS_AUDIO_FPATH = THIS_DIR / "speech.mp3"

app = FastAPI(docs_url="/")

# Mock response configuration
mock_responses = [
    {
        "httpRequest": {"method": "POST", "path": "/chat/completions"},
        "httpResponse": {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": {
                "id": "chatcmpl-6lX3c8j6jNfOo0zHvX56A1E7",
                "object": "chat.completion",
                "created": 1677628902,
                "model": "gpt-4-0314",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "This is a mock response from the chat completion endpoint.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 9, "completion_tokens": 14, "total_tokens": 23},
            },
        },
    },
    {
        "httpRequest": {"method": "POST", "path": "/images/generations"},
        "httpResponse": {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": {
                "id": "imggen-9X3c8j6jNfOo0zHvX56A1E7",
                "object": "image.generation",
                "created": 1677628902,
                "model": "dall-e-2024",
                "data": [
                    {
                        "url": "https://repository-images.githubusercontent.com/516708998/571919ae-d303-406d-8098-af4b2d2fb6be"
                    }
                ],
                "usage": {"prompt_tokens": 15, "completion_tokens": 1, "total_tokens": 16},
            },
        },
    },
]


@app.post("/chat/completions")
async def chat_completions():
    response_config = mock_responses[0]["httpResponse"]
    return JSONResponse(
        content=response_config["body"],
        status_code=response_config["statusCode"],
        headers=response_config["headers"],
    )


@app.post("/images/generations")
async def images_generations():
    response_config = mock_responses[1]["httpResponse"]
    return JSONResponse(
        content=response_config["body"],
        status_code=response_config["statusCode"],
        headers=response_config["headers"],
    )


@app.post("/audio/speech")
async def create_speech():
    """Return the local speech.mp3 file as a streaming response."""
    mp3_content = BytesIO(SAMPLE_TTS_AUDIO_FPATH.read_bytes())
    return StreamingResponse(content=mp3_content, media_type="audio/mpeg", headers={"Transfer-Encoding": "chunked"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=MOCK_PORT)
