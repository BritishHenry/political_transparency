'''

This file will be used to orchestrate the whole document handling process, from upload to chat-ready.

Methods should be imported into here from across the app to manage the whole pipeline efficiently and in one place.

This can also be used as a single source of truth for any key variables.

'''
from django.shortcuts import get_object_or_404

from services.ai.chunking.utils import upload_file_to_openai, get_document_structure, get_document_chunks, save_chunks
from services.ai.embedding.utils import embed_chunk, save_embedding

from document_manager.models.chunking import DocumentChunk
from document_manager.models.general import Document

from services.ai.chunking.chunker import PDFDocumentChunker

from openai import OpenAI

import logging
logger = logging.getLogger(__name__)

### Control class to orchestrate the whole document handling from upload to chat-ready.

class Control():

    def __init__(self):
        self.chunking_model = "gpt-4.1"
        self.embedding_model = "text-embedding-3-small" # need to add

    def chunk_document(self, document):
        try:
            llm_service = OpenAI()
            chunker = PDFDocumentChunker(document=document, llm_service=llm_service, chunking_model=self.chunking_model)
            chunker.process_document()
        except Exception as e:
            logger.error("Failed to chunk document | Error msg: ", e)
            