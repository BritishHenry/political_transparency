'''
Use this to seperate out concerns. 
Embedding-related validation should happen here.
'''
import logging
logger = logging.getLogger(__name__)

def validate_embedding_input(text:str) -> bool:
    """Validate text input for embedding generation."""

    if not isinstance(text, str):
        raise TypeError(f"Expected string, got {type(text)}")
    
    if not text or not text.strip():
        raise ValueError("Empty or whitespace-only text provided")

    # Check if text is too long (OpenAI has token limits)
    if len(text) > 32000:  # Rough character limit: ~32k chars (≈8k tokens)
        raise ValueError(f"Text length {len(text)} exceeds maximum (~32,000 characters)")

    return True

def validate_embedding_response(response, expected_size):
    """Validate the embedding response from OpenAI"""
    if not response or not response.data:
        raise ValueError("Empty response from embedding API")
    
    if len(response.data) == 0:
        raise ValueError("No embedding data in response")
    
    embedding = response.data[0].embedding
    
    if not isinstance(embedding, list):
        raise ValueError(f"Embedding is not a list: {type(embedding)}")
    
    if len(embedding) != expected_size:
        raise ValueError(f"Embedding dimension mismatch: got {len(embedding)}, expected {expected_size}")
    
    # Check for invalid values
    if not all(isinstance(x, (int, float)) for x in embedding):
        raise ValueError("Embedding contains non-numeric values")
    
    return embedding