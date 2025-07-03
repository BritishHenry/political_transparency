from services.ai.embedding.embedder import Embedder
from openai import OpenAI
from django.conf import settings
import requests
import re
from chat_manager import prompts
from django.shortcuts import get_object_or_404
from apps.document_manager.models import DocumentChunk, DocumentSummary

def generate_response(response_params):
    
    openai_client = OpenAI()

    # Step 1: embed the message
    embedder = Embedder(
        llm_service=openai_client, 
        embedding_model="text-embedding-3-small", # Embedding model must be the same as the doc embedding
    ) 
    embedding = embedder.get_embedding(response_params["message"])


    # Step 2: semantic search of vector db
    collection_name = response_params["collection_name"]
    # Search points (POST /collections/:collection_name/points/search)
    search_results = requests.post(
        f"{settings.QDRANT_POLITICAL_TRANSPARENCY_ENDPOINT}/collections/{collection_name}/points/search",
        headers={
            settings.QDRANT_API_KEY
        },
        json={
            "vector": embedding,
            "limit": 5 # Max number of results to return
        },
    )

    # Step 3: get texts from postgre for the vectors
    texts = []
    for result in search_results:
        if result['model'] == 'DocumentSummary':
            text = get_object_or_404(DocumentSummary, pk=result['object_id'])
        elif result['model'] == 'DocumentChunk':
            text = get_object_or_404(DocumentChunk, pk=result['object_id'])
        texts.append(text)

    # Generate a single string with subheadings
    string_of_texts = "\n\n".join(
        f"### Chunk {i+1}\n\n{item}" for i, item in enumerate(texts)
    )

    # Step 4: call ai to generate answer
    response = openai_client.responses.create(
                model = "gpt-4",
                instructions = prompts.response_generation_instructions, 
                input = prompts.response_generation_input(response_params["message"], string_of_texts)
            )
            
    cleaned_response =  response.output_text.strip()

    #response = "wagwan General, I am AI."
    return cleaned_response #this saves to the Task ojects's result field: task.result
