'''

This file will be used to orchestrate the whole document handling process, from upload to chat-ready.

Methods should be imported into here from across the app to manage the whole pipeline efficiently and in one place.

This can also be used as a single source of truth for any key variables.

'''
from django.shortcuts import get_object_or_404

from document_manager.chunking.utils import upload_file_to_openai, get_document_chunks, save_chunks
from document_manager.embedding.utils import embed_chunk, save_embedding

from document_manager.models.chunking import DocumentChunk
from document_manager.models.general import Document

from openai import OpenAI

import logging
logger = logging.getLogger(__name__)

### Control class to orchestrate the whole document handling from upload to chat-ready.

class Control():

    chunking_model = "gpt-4.1"
    embedding_model = ""

    def __init__(self, chunking_model, embedding_model):
        self.chunking_model = chunking_model
        self.embedding_model = embedding_model


    def get_text_chunks(self, document_id):
        try:
            document = get_object_or_404(Document, id = document_id)

            client = OpenAI()

            uploaded_file = upload_file_to_openai(client, document.file)
            json_chunks = get_document_chunks(client, self.chunking_model, uploaded_file) # Returns as json object

            saved_chunks = save_chunks(json_chunks, document_id) # Returns queryset

            return saved_chunks 
        
        except Exception as e:
            logger.warning(f"Error occured while getting text chunks from the document | Error: {e}")

    def embed_chunks(self, document_id):

        try:
            client = OpenAI()

            text_chunks = DocumentChunk.objects.filter(document__id = document_id).order_by('chunk_index')

            for text_chunk in text_chunks:

                # Get embedding from text
                embeded_chunk = embed_chunk(client, self.embedding_model, text_chunk)

                # Save embedding to vector database
                saved_vector_chunk_id = save_embedding(embeded_chunk)

                # Save vector database instance ID to the related DocumentChunk
                text_chunk.vector_id = saved_vector_chunk_id
                text_chunk.save()

        except Exception as e:
            logger.warning(f"Error occured while embedding and saving the embeddings of the DocumentChunks | Error: {e}")