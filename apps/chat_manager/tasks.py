from services.ai.embedding.embedder import Embedder
from openai import OpenAI
from django.conf import settings
import requests
import re
from chat_manager import prompts
from django.shortcuts import get_object_or_404
from document_manager.models import DocumentChunk, DocumentSummary
from django.conf import settings

import logging
logger = logging.getLogger(__name__)

def generate_response(response_params):
    try:
        #print("response params: ", response_params)
        # Initialise OpenAI client
        openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        #print("initialised openai client")

        # Step 1: embed the message
        embedder = Embedder(
            llm_service=openai_client, 
            embedding_model="text-embedding-3-small", # Embedding model must be the same as the doc embedding
        ) 
        embedding = embedder.get_embedding(response_params["message"])
        #print(f"Embedded the message.")


        # Step 2: semantic search of vector db
        collection_name = response_params["collection_name"]
        search_results = embedder.qdrant_client.query_points(
            collection_name = collection_name,
            query=embedding,
            limit=5,
        )
        #print("Searched vector storage.")
        print("Search results: ", search_results)

        # Step 3: get texts from postgre for the vectors
        texts = []
        for result in search_results.points:
            if hasattr(result, 'payload'):
                payload = result.payload
            else:
                payload = dict(result[0])['payload'] if isinstance(result, (list, tuple)) else result['payload']

            #print("Type: ", payload['type'])
            if payload['type'] in ['document', 'summary']: # DocumentSummary
                text = get_object_or_404(DocumentSummary, pk=int(payload['object_id'])).content
            else: #DocumentChunk
                text = get_object_or_404(DocumentChunk, pk=int(payload['object_id'])).content
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
        #print("Got a user response from OpenAI.")
        cleaned_response =  response.output_text.strip()

        #response = "wagwan General, I am AI."
        return cleaned_response #this saves to the Task ojects's result field: task.result
    except Exception as e:
        logger.error(f"Error creating response to user | Error: {e}")
        return "Error creating response."