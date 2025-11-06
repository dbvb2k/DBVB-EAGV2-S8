import os
import json
import yaml
import requests
import asyncio
import time
from pathlib import Path
from google import genai
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
MODELS_JSON = ROOT / "config" / "models.json"
PROFILE_YAML = ROOT / "config" / "profiles.yaml"

class ModelManager:
    def __init__(self):
        self.config = json.loads(MODELS_JSON.read_text())
        self.profile = yaml.safe_load(PROFILE_YAML.read_text())

        self.text_model_key = self.profile["llm"]["text_generation"]
        self.model_info = self.config["models"][self.text_model_key]
        self.model_type = self.model_info["type"]

        # ✅ Gemini initialization (your style)
        if self.model_type == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            # Fallback to config.py if environment variable not set
            if not api_key:
                try:
                    import config
                    api_key = getattr(config, "GEMINI_API_KEY", None)
                except ImportError:
                    pass
            
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY not found. Set it as environment variable "
                    "or in config.py"
                )
            
            self.client = genai.Client(api_key=api_key)

    async def generate_text(self, prompt: str) -> str:
        if self.model_type == "gemini":
            return self._gemini_generate(prompt)

        elif self.model_type == "ollama":
            return self._ollama_generate(prompt)

        raise NotImplementedError(f"Unsupported model type: {self.model_type}")

    def _gemini_generate(self, prompt: str, max_retries: int = 3) -> str:
        """Generate text using Gemini API with retry logic for rate limits."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_info["model"],
                    contents=prompt
                )

                # ✅ Safely extract response text
                try:
                    return response.text.strip()
                except AttributeError:
                    try:
                        return response.candidates[0].content.parts[0].text.strip()
                    except Exception:
                        return str(response)
                        
            except Exception as e:
                error_str = str(e)
                last_error = e
                
                # Check if it's a rate limit error (429)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        # Exponential backoff: wait 2^attempt seconds
                        wait_time = 2 ** attempt
                        print(f"[WARNING] Rate limit hit, retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"[ERROR] Rate limit exceeded after {max_retries} attempts. Please wait a few minutes and try again.")
                        raise Exception(f"Gemini API rate limit exceeded: {error_str}")
                else:
                    # For other errors, don't retry
                    raise
        
        # If we get here, all retries failed
        raise Exception(f"Failed to generate text after {max_retries} attempts: {last_error}")

    def _ollama_generate(self, prompt: str) -> str:
        response = requests.post(
            self.model_info["url"]["generate"],
            json={"model": self.model_info["model"], "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        return response.json()["response"].strip()
