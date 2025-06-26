"""Load/e2e test for the Files API.

Note, if you ever want to incorporate AWS SigV4 auth, it is straightforward. Reference
this SO answer: https://stackoverflow.com/questions/74002094/aws-authentication-in-locust-io-python
"""

import random

from locust import HttpUser, between, task


class FilesAPIUser(HttpUser):
    """Locust user class for the Files API."""

    wait_time = between(1, 5)

    @task
    def file_operations_flow(self):
        file_path = f"test_file_{random.randint(1000, 9999)}.txt"
        file_content = b"This is a test file content."

        # 0. List files
        self.client.get("/v1/files", name="List Files")

        # 1. Upload file
        files = {"file_content": (file_path, file_content, "text/plain")}
        self.client.put(f"/v1/files/{file_path}", files=files, name="Upload File")

        # 2. Describe the file (HEAD request)
        self.client.head(f"/v1/files/{file_path}", name="Describe File")

        # 3. List files again
        self.client.get("/v1/files", name="List Files (After Upload)")

        # 4. Download the file
        self.client.get(f"/v1/files/{file_path}", name="Download File")

        # 5. Delete the file
        self.client.delete(f"/v1/files/{file_path}", name="Delete File")

    @task
    def generate_ai_files_flow(self):
        # Generate a text file
        text_file_path = f"ai_text_{random.randint(1000, 9999)}.txt"
        text_request_body = {
            "file_path": text_file_path,
            "prompt": "Write a short poem about clouds",
            "file_type": "text",
        }
        self.client.post("/v1/files/generated", json=text_request_body, name="Generate AI Text")

        # Generate an image file
        image_file_path = f"ai_image_{random.randint(1000, 9999)}.png"
        image_request_body = {
            "file_path": image_file_path,
            "prompt": "A beautiful landscape with mountains and a lake",
            "file_type": "image",
        }
        self.client.post("/v1/files/generated", json=image_request_body, name="Generate AI Image")

        # Generate an audio file
        audio_file_path = f"ai_audio_{random.randint(1000, 9999)}.mp3"
        audio_request_body = {
            "file_path": audio_file_path,
            "prompt": "Generate a short text-to-speech audio saying 'Welcome to our API'",
            "file_type": "text-to-speech",
        }
        self.client.post("/v1/files/generated", json=audio_request_body, name="Generate AI Audio")
