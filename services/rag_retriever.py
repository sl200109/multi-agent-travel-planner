from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from services.ollama_embedding_client import OllamaEmbeddingClient


DEFAULT_DB_DIR = PROJECT_ROOT / "data" / "chroma_db"
DEFAULT_COLLECTION = "travel_knowledge"


class RagRetriever:
    """
    本地 RAG 检索器。

    它负责把：
    用户问题 -> query embedding -> ChromaDB 相似度检索 -> top-k chunk

    这里不负责生成回答，只负责找资料。
    """

    def __init__(
        self,
        db_dir: Path | str = DEFAULT_DB_DIR,
        collection_name: str = DEFAULT_COLLECTION,
        ollama_url: str = "http://localhost:11434",
        model: str = "qwen3-embedding:0.6b",
    ) -> None:
        self.db_dir = Path(db_dir)
        self.collection_name = collection_name

        self.embedding_client = OllamaEmbeddingClient(
            model=model,
            base_url=ollama_url,
        )

        self.chroma_client = chromadb.PersistentClient(path=str(self.db_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name
        )

    def retrieve(
        self,
        query: str,
        city: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        根据 query 检索最相关的 top-k chunks。

        参数：
            query: 用户问题
            city: 可选城市过滤，例如 "chengdu"
            top_k: 返回几个最相关 chunk

        返回：
            [
                {
                    "content": "...",
                    "metadata": {...},
                    "distance": 0.123
                }
            ]
        """
        if not query.strip():
            raise ValueError("query cannot be empty")

        query_embedding = self.embedding_client.embed_one(query)

        where = None
        if city:
            where = {"city": city}

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        results: List[Dict[str, Any]] = []

        for doc, metadata, distance in zip(documents, metadatas, distances):
            results.append(
                {
                    "content": doc,
                    "metadata": metadata,
                    "distance": distance,
                }
            )

        return results

    @staticmethod
    def format_context(results: List[Dict[str, Any]]) -> str:
        """
        把检索结果格式化成人能看懂的文本。

        后续也可以直接把这个字符串拼进 prompt。
        """
        if not results:
            return "No RAG results found."

        blocks = []

        for idx, item in enumerate(results, start=1):
            metadata = item.get("metadata", {})
            content = item.get("content", "")
            distance = item.get("distance", "")

            city_zh = metadata.get("city_zh", "")
            source_file = metadata.get("source_file", "")
            section_title = metadata.get("section_title", "")

            blocks.append(
                f"[RAG-{idx}]\n"
                f"City: {city_zh}\n"
                f"Source: {source_file}\n"
                f"Section: {section_title}\n"
                f"Distance: {distance}\n"
                f"Content:\n{content}"
            )

        return "\n\n".join(blocks)