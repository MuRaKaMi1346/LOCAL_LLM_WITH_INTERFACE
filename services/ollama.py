import httpx
import logging

from config import settings

logger = logging.getLogger(__name__)


class OllamaService:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.chat_model = settings.ollama_chat_model
        self.embed_model = settings.ollama_embed_model
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat(self, messages: list[dict], system_prompt: str | None = None) -> str:
        all_messages: list[dict] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)
        payload = {
            "model": self.chat_model,
            "messages": all_messages,
            "stream": False,
            "options": {"temperature": 0.5, "top_p": 0.9, "num_ctx": 8192},
        }
        try:
            r = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self.base_url)
            raise ConnectionError("Ollama ไม่ตอบสนอง กรุณาตรวจสอบว่า Ollama กำลังทำงานอยู่")
        except Exception as e:
            logger.error("Ollama chat error: %s", e)
            raise

    async def embed(self, text: str) -> list[float]:
        try:
            r = await self.client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.embed_model, "input": text},
            )
            r.raise_for_status()
            data = r.json()
            embeddings = data.get("embeddings") or data.get("embedding")
            return embeddings[0] if isinstance(embeddings[0], list) else embeddings
        except httpx.ConnectError:
            raise ConnectionError("Ollama ไม่ตอบสนอง")
        except Exception as e:
            logger.error("Ollama embed error: %s", e)
            raise

    async def list_models(self) -> list[str]:
        try:
            r = await self.client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    async def is_healthy(self) -> bool:
        try:
            r = await self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()


ollama = OllamaService()
