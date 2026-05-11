import asyncio
import os
import shutil
import subprocess
import sys

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
            if not embeddings:
                raise ValueError(f"Ollama embed returned no embeddings: {data}")
            first = embeddings[0]
            return first if isinstance(first, list) else embeddings
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

    def _find_binary(self) -> str | None:
        found = shutil.which("ollama")
        if found:
            return found
        if sys.platform == "win32":
            candidates = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                r"C:\Program Files\Ollama\ollama.exe",
            ]
        else:
            candidates = ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama", "/usr/bin/ollama"]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    async def model_available(self, model: str) -> bool:
        available = await self.list_models()
        base_name = model.split(":")[0]
        return (
            model in available
            or f"{model}:latest" in available
            or base_name in available
            or any(m.split(":")[0] == base_name for m in available)
        )

    async def ensure_running(self) -> bool:
        """Start Ollama headlessly if not already running. Returns True once API is up."""
        if await self.is_healthy():
            return True

        cmd = self._find_binary()
        if not cmd:
            logger.warning("Ollama binary not found — cannot auto-start")
            return False

        logger.info("Ollama not responding — attempting to start...")

        # macOS: brew services first (persists across reboots)
        if sys.platform == "darwin":
            brew = shutil.which("brew")
            if not brew:
                for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
                    if os.path.isfile(p):
                        brew = p
                        break
            if brew:
                try:
                    subprocess.run([brew, "services", "start", "ollama"],
                                   capture_output=True, timeout=20)
                    for _ in range(10):
                        await asyncio.sleep(1)
                        if await self.is_healthy():
                            logger.info("Ollama started via brew services")
                            return True
                except Exception:
                    pass

        # Generic fallback: ollama serve detached
        try:
            env = os.environ.copy()
            host = self.base_url.removeprefix("http://").removeprefix("https://")
            env["OLLAMA_HOST"] = host
            if sys.platform == "win32":
                subprocess.Popen(
                    [cmd, "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                                   | subprocess.DETACHED_PROCESS),
                    env=env,
                )
            else:
                subprocess.Popen(
                    [cmd, "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
        except Exception as e:
            logger.error("Failed to launch Ollama: %s", e)
            return False

        for _ in range(30):
            await asyncio.sleep(1)
            if await self.is_healthy():
                logger.info("Ollama server started successfully")
                return True

        logger.error("Ollama did not respond within 30 s — start manually: ollama serve")
        return False

    async def close(self):
        await self.client.aclose()


ollama = OllamaService()
