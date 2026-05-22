from __future__ import annotations

from typing import List

import requests


class OllamaEmbeddingClient:
    """
    用于调用本地 Ollama embedding API 的客户端。

    当前默认使用：
    - Ollama 地址：http://localhost:11434
    - embedding 模型：qwen3-embedding:0.6b
    """

    def __init__(
        self,
        model: str = "qwen3-embedding:0.6b",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成 embedding。

        参数：
            texts: 多段文本，例如 ["成都三天怎么玩", "北京亲子研学路线"]

        返回：
            每段文本对应一个向量，例如：
            [
                [0.01, 0.02, ...],
                [0.03, 0.04, ...],
            ]
        """
        if not texts:
            return []

        response = requests.post(
            f"{self.base_url}/api/embed",
            json={
                "model": self.model,
                "input": texts,
            },
            timeout=self.timeout,
        )

        if response.status_code != 200:
            raise RuntimeError(
                "Ollama embedding request failed. "
                f"status={response.status_code}, body={response.text}"
            )

        data = response.json()
        embeddings = data.get("embeddings")

        if not isinstance(embeddings, list):
            raise RuntimeError(f"Invalid Ollama embedding response: {data}")

        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
            )

        return embeddings

    def embed_one(self, text: str) -> List[float]:
        """
        给单条文本生成 embedding。
        """
        embeddings = self.embed([text])
        if not embeddings:
            raise RuntimeError("Ollama returned empty embedding.")
        return embeddings[0]