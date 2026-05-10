import logging
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings
from services.ollama import ollama

logger = logging.getLogger(__name__)
COLLECTION_NAME = "faculty_knowledge"


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    paragraphs = re.split(r"\n{2,}", text.strip())
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            if len(para) <= chunk_size:
                overlap_text = current[-overlap:] if current and overlap else ""
                current = (overlap_text + "\n\n" + para).strip() if overlap_text else para
            else:
                sentences = re.split(r"(?<=[.!?।।])\s+", para)
                sub = ""
                for sent in sentences:
                    if len(sub) + len(sent) + 1 <= chunk_size:
                        sub = (sub + " " + sent).strip()
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = sent
                current = sub
    if current:
        chunks.append(current)
    return chunks


class RAGService:
    def __init__(self):
        self.client = chromadb.Client(
            ChromaSettings(anonymized_telemetry=False, allow_reset=True)
        )
        self.collection = None
        self._ready = False

    async def build_index(self, data_dir: str = "data") -> int:
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        if self.collection.count() > 0:
            logger.info("RAG index already has %d chunks", self.collection.count())
            self._ready = True
            return self.collection.count()

        data_path = Path(data_dir)
        docs = list(data_path.glob("**/*.md")) + list(data_path.glob("**/*.txt"))
        if not docs:
            logger.warning("No documents found in %s", data_dir)
            return 0

        all_chunks, all_ids = [], []
        for doc_path in docs:
            text = doc_path.read_text(encoding="utf-8")
            chunks = _chunk_text(text, settings.chunk_size, settings.chunk_overlap)
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_ids.append(f"{doc_path.stem}_{i}")

        logger.info("Embedding %d chunks from %d files...", len(all_chunks), len(docs))
        all_embeddings: list[list[float]] = []
        for text in all_chunks:
            all_embeddings.append(await ollama.embed(text))

        self.collection.add(documents=all_chunks, embeddings=all_embeddings, ids=all_ids)
        self._ready = True
        logger.info("RAG index built with %d chunks", len(all_chunks))
        return len(all_chunks)

    async def retrieve(self, query: str, top_k: int | None = None) -> list[str]:
        if not self._ready or self.collection is None:
            return []
        k = top_k or settings.rag_top_k
        query_emb = await ollama.embed(query)
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=min(k, self.collection.count()),
        )
        return results.get("documents", [[]])[0]

    async def retrieve_with_scores(self, query: str, top_k: int | None = None) -> list[dict]:
        if not self._ready or self.collection is None:
            return []
        k = top_k or settings.rag_top_k
        query_emb = await ollama.embed(query)
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=min(k, self.collection.count()),
            include=["documents", "distances"],
        )
        docs = results.get("documents", [[]])[0]
        dists = results.get("distances", [[]])[0]
        return [
            {"text": doc, "score": round(max(0.0, 1.0 - dist) * 100, 1)}
            for doc, dist in zip(docs, dists)
        ]

    async def retrieve_as_context(self, query: str) -> str:
        chunks = await self.retrieve(query)
        return "\n\n---\n\n".join(chunks) if chunks else ""

    async def reset_and_rebuild(self, data_dir: str = "data") -> int:
        if self.collection:
            self.client.delete_collection(COLLECTION_NAME)
        self._ready = False
        self.collection = None
        return await self.build_index(data_dir)

    @property
    def is_ready(self) -> bool:
        return self._ready


rag = RAGService()
