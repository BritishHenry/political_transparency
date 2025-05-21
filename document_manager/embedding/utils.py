from document_manager.models.chunking import DocumentChunk

import logging
logger = logging.getLogger(__name__)

def embed_chunk(client, model, text_chunk):
    # API reference to see example output etc: https://platform.openai.com/docs/guides/embeddings

    try:
        response = client.embeddings.create(
            input=text_chunk,
            model = model
        )
        return response.data[0].embedding
    
    except Exception as e:
        logger.warning(f"Failed to embed text chunk with OpenAI | Error: {e}")

def save_embedding(embedding_data):
    # Receieve an embedding and save it to the vector database
    return
