from services.ai.chunking.system_prompts import get_chunks_prompt, get_structure_prompt
from apps.document_manager.models.chunking import DocumentChunk
from apps.document_manager.models.general import Document

from django.shortcuts import get_object_or_404
from django.utils import timezone

import json

import logging
logger = logging.getLogger(__name__)

def upload_file_to_openai(client, file):
    try:
        uploaded_file = client.files.create(
            file=file,
            purpose="user_data",  # there are 4 options for 'purpose' and user_data is the most flexible. The options: fine-tune: Used for fine-tuning - vision: Images used for vision fine-tuning - user_data: Flexible file type for any purpose - evals: Used for eval data sets
        )
    except Exception as e:
        logger.warning(f"Failed to upload file to OpenAI | Error: {e}")

    return uploaded_file

def get_document_structure(client, model, uploaded_file):
    try:
        structure = client.responses.create(
            model = model,
            input = [
                {
                    "role":"user",
                    "content": [
                        {
                            "type": "input_file",
                            "file_id": uploaded_file.id,
                        },
                        {
                            "type": "input_text",
                            "text": get_structure_prompt,
                        },
                    ]
                }
            ],
            response_format={ #Not sure if this will work.
                "type": "json_schema",
            }
        )

        json_structure = json.loads(structure)

    except Exception as e:
        logger.warning(f"Failed to get document structure for the embedding with OpenAI | Error: {e}")

    return json_structure

def get_document_chunks(client, model, uploaded_file, document_structure):
    try:
        
        chunks = {}
        for level in document_structure:
            
            # Coherently appends the level to the end of the prompt, so the LLM knows how to chunk.
            prompt = f"{get_chunks_prompt} {level}"

            # Only models that support both text and image inputs, such as gpt-4o, gpt-4o-mini, or o1, can accept PDF files as input.
            chunks[level] = client.responses.create(
                model = model,
                input = [
                    {
                        "role":"user",
                        "content": [
                            {
                                "type": "input_file",
                                "file_id": uploaded_file.id,
                            },
                            {
                                "type": "input_text",
                                "text": prompt,
                            },
                        ]
                    }
                ]
            )
        
        # chunks returns a string with json inside
        # json.loads turns that into a (pythonic) json object
        # json_chunks = json.loads(chunks)

    except Exception as e:
        logger.warning(f"Failed to get text chunks from document for the embedding with OpenAI | Error: {e}")

    return chunks

def save_chunks(json_chunks, document_id):
    try:
        document = get_object_or_404(Document, id = document_id)
        # Get datetime

        document_chunk_ids = []
        
        counter = 1
        for chunk in json_chunks:
            content = chunk[''] #get the item form the json

            new_chunk = DocumentChunk(
                document=document, 
                chunk_index = counter,
                content = content,
                created_at = timezone.now()
                )
            new_chunk.save()

            document_chunk_ids.append(new_chunk.id)

            counter += 1
        
        # Return queryset of all newly saved chunks
        saved_chunks = DocumentChunk.objects.filter(id__in = document_chunk_ids)

        return saved_chunks

    except Exception as e:
        logger.warning(f"Could not save chunks from json | Error: {e}")
