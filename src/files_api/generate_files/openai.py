"""Generate text, images, and audio from prompts using OpenAI's API."""

from typing import (
    Literal,
    Optional,
    Tuple,
    Union,
)

from aws_embedded_metrics import MetricsLogger
from aws_embedded_metrics.storage_resolution import StorageResolution
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from files_api.monitoring.metrics import metrics_ctx

SYSTEM_PROMPT = "You are an autocompletion tool that produces text files given constraints."


async def get_text_chat_completion(prompt: str, openai_client: Optional[AsyncOpenAI] = None) -> str:
    """Generate a text chat completion from a given prompt."""
    # get the OpenAI client
    client = openai_client or AsyncOpenAI()

    # get the completion
    response: ChatCompletion = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=100,  # avoid burning your credits
        n=1,  # number of responses
    )

    metrics: MetricsLogger | None = metrics_ctx.get()
    if metrics:
        metrics.put_metric(
            key="OpenAITokensUsage",
            value=response.usage.total_tokens,
            unit="Count",
            storage_resolution=StorageResolution.STANDARD,
        )
    return response.choices[0].message.content or ""


async def generate_image(prompt: str, openai_client: Optional[AsyncOpenAI] = None) -> Union[str, None]:
    """Generate an image from a given prompt."""
    # get the OpenAI client
    client = openai_client or AsyncOpenAI()

    # get image response from OpenAI
    image_response = await client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )

    metrics: MetricsLogger | None = metrics_ctx.get()
    if metrics:
        metrics.put_metric(key="OpenAIImageGeneratedCount", value=1, unit="Count")

    return image_response.data[0].url or None


async def generate_text_to_speech(
    prompt: str,
    openai_client: Optional[AsyncOpenAI] = None,
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3",
) -> Tuple[bytes, str]:
    """
    Generate text-to-speech audio from a given prompt.

    Returns the audio content as bytes and the MIME type as a string.
    """
    # get the OpenAI client
    client = openai_client or AsyncOpenAI()

    # get audio response from OpenAI
    audio_response = await client.audio.speech.with_raw_response.create(
        model="tts-1",
        voice="echo",
        input=prompt,
        response_format=response_format,
    )

    # Get the audio content as bytes
    file_content_bytes: bytes = audio_response.content
    file_mime_type: str = audio_response.headers.get("Content-Type")

    metrics: MetricsLogger | None = metrics_ctx.get()
    if metrics:
        metrics.put_metric(key="OpenAITextToSpeechGeneratedCount", value=1, unit="Count")

    return file_content_bytes, file_mime_type
