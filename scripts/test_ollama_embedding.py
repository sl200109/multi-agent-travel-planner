from services.ollama_embedding_client import OllamaEmbeddingClient


def main() -> None:
    client = OllamaEmbeddingClient()

    text = "成都三天亲子美食怎么安排"
    embedding = client.embed_one(text)

    print("Input text:")
    print(text)

    print("\nEmbedding dimension:")
    print(len(embedding))

    print("\nFirst 10 values:")
    print(embedding[:10])


if __name__ == "__main__":
    main()