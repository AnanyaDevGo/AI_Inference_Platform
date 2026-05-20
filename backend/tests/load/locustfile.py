import json
from locust import HttpUser, task, between

class InferenceUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def chat_completion(self):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-12345"  # You should replace this with a valid key for testing
        }
        
        payload = {
            "model": "llama3.2:3b",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "stream": False
        }
        
        with self.client.post("/v1/chat/completions", headers=headers, json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status code: {response.status_code}")
