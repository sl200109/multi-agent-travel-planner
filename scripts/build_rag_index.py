from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb
import yaml
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from services.ollama_embedding_client import OllamaEmbeddingClient


DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "rag_sources" / "china_travel"
DEFAULT_DB_DIR = PROJECT_ROOT / "data" / "chroma_db"
DEFAULT_COLLECTION = "travel_knowledge"


def parse_front_matter(md_text: str, file_path: Path) -> Tuple[Dict[str, Any], str]:
    """
    解析 Markdown 文件开头的 YAML front matter。

    返回：
    - metadata: city、city_zh、province、region 等
    - body: 去掉 YAML 后的正文
    """
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, md_text, flags=re.DOTALL)

    if match:
        yaml_text = match.group(1)
        body = md_text[match.end():]
        metadata = yaml.safe_load(yaml_text) or {}
    else:
        metadata = {}
        body = md_text

    metadata.setdefault("city", file_path.stem)
    metadata.setdefault("city_zh", file_path.stem)
    metadata.setdefault("province", "")
    metadata.setdefault("region", "")

    return metadata, body.strip()


def normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    ChromaDB metadata 不能随便存复杂对象。
    这里把 list 转成逗号分隔字符串。
    """
    normalized: Dict[str, Any] = {}

    for key, value in metadata.items():
        if isinstance(value, list):
            normalized[key] = ",".join(str(v) for v in value)
        elif isinstance(value, dict):
            normalized[key] = str(value)
        elif value is None:
            normalized[key] = ""
        else:
            normalized[key] = value

    return normalized


def split_by_sections(body: str) -> List[Tuple[str, str]]:
    """
    按 Markdown 二级标题 ## 切分。

    例如：
    ## 1. 城市画像
    ## 2. 适合人群
    ## 8. 经典路线模板
    """
    lines = body.splitlines()

    sections: List[Tuple[str, List[str]]] = []
    current_title = "# Introduction"
    current_lines: List[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, current_lines))

            current_title = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    results: List[Tuple[str, str]] = []
    for title, section_lines in sections:
        section_text = "\n".join(section_lines).strip()
        if section_text:
            results.append((title, section_text))

    return results


def sliding_window_split(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    如果某个 section 太长，就继续滑窗切 chunk。
    """
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be larger than overlap")

    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks


def make_chunk_id(
    source_file: str,
    section_title: str,
    chunk_index: int,
    chunk_text: str,
) -> str:
    """
    生成稳定 chunk id。
    重复建库时同一段内容 id 一样，upsert 会覆盖，不会重复插入。
    """
    raw = f"{source_file}|{section_title}|{chunk_index}|{chunk_text}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_chunks_from_file(
    file_path: Path,
    chunk_size: int,
    overlap: int,
) -> List[Dict[str, Any]]:
    md_text = file_path.read_text(encoding="utf-8")

    raw_metadata, body = parse_front_matter(md_text, file_path)
    raw_metadata = normalize_metadata(raw_metadata)

    sections = split_by_sections(body)

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for section_title, section_text in sections:
        section_chunks = sliding_window_split(
            text=section_text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        for chunk_text in section_chunks:
            chunk_id = make_chunk_id(
                source_file=file_path.name,
                section_title=section_title,
                chunk_index=chunk_index,
                chunk_text=chunk_text,
            )

            metadata: Dict[str, Any] = {
                "city": raw_metadata.get("city", file_path.stem),
                "city_zh": raw_metadata.get("city_zh", file_path.stem),
                "province": raw_metadata.get("province", ""),
                "region": raw_metadata.get("region", ""),
                "source_file": file_path.name,
                "section_title": section_title,
                "chunk_index": chunk_index,
                "chunk_id": chunk_id,
            }

            for key in [
                "tags",
                "best_months",
                "recommended_days",
                "suitable_styles",
                "budget_level",
            ]:
                if key in raw_metadata:
                    metadata[key] = raw_metadata[key]

            chunks.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": metadata,
                }
            )

            chunk_index += 1

    return chunks


def load_all_chunks(source_dir: Path, chunk_size: int, overlap: int) -> List[Dict[str, Any]]:
    md_files = sorted(source_dir.glob("*.md"))

    if not md_files:
        raise FileNotFoundError(f"No Markdown files found in: {source_dir}")

    all_chunks: List[Dict[str, Any]] = []

    for file_path in md_files:
        file_chunks = build_chunks_from_file(
            file_path=file_path,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        all_chunks.extend(file_chunks)

    return all_chunks


def batch_items(items: List[Any], batch_size: int) -> List[List[Any]]:
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def build_index(args: argparse.Namespace) -> None:
    source_dir = Path(args.source_dir)
    db_dir = Path(args.db_dir)

    print(f"[INFO] Source dir: {source_dir}")
    print(f"[INFO] DB dir: {db_dir}")
    print(f"[INFO] Collection: {args.collection}")
    print(f"[INFO] Ollama URL: {args.ollama_url}")
    print(f"[INFO] Embedding model: {args.model}")

    db_dir.mkdir(parents=True, exist_ok=True)

    chunks = load_all_chunks(
        source_dir=source_dir,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )

    print(f"[INFO] Total chunks: {len(chunks)}")

    embedding_client = OllamaEmbeddingClient(
        model=args.model,
        base_url=args.ollama_url,
        timeout=args.timeout,
    )

    chroma_client = chromadb.PersistentClient(path=str(db_dir))

    if args.reset:
        try:
            chroma_client.delete_collection(args.collection)
            print(f"[INFO] Deleted old collection: {args.collection}")
        except Exception:
            print("[INFO] No old collection to delete.")

    collection = chroma_client.get_or_create_collection(name=args.collection)

    batches = batch_items(chunks, args.batch_size)

    for batch in tqdm(batches, desc="Building ChromaDB index"):
        ids = [item["id"] for item in batch]
        documents = [item["text"] for item in batch]
        metadatas = [item["metadata"] for item in batch]

        embeddings = embedding_client.embed(documents)

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    print("[DONE] Local RAG vector database built successfully.")
    print(f"[DONE] DB path: {db_dir}")
    print(f"[DONE] Collection: {args.collection}")
    print(f"[DONE] Collection count: {collection.count()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build local ChromaDB RAG index from travel Markdown files."
    )

    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Directory containing city Markdown files.",
    )
    parser.add_argument(
        "--db-dir",
        default=str(DEFAULT_DB_DIR),
        help="ChromaDB persistence directory.",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="ChromaDB collection name.",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL.",
    )
    parser.add_argument(
        "--model",
        default="qwen3-embedding:0.6b",
        help="Ollama embedding model name.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=800,
        help="Max chunk size in characters.",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=120,
        help="Overlap size for long chunks.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size for embedding requests.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout seconds for Ollama embedding requests.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete old collection before rebuilding.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    build_index(parse_args())