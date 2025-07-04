'''

This file will be used to orchestrate the whole document handling process, from upload to chat-ready.

Methods should be imported into here from across the app to manage the whole pipeline efficiently and in one place.

This can also be used as a single source of truth for any key variables.

'''

from services.ai.chunking.chunker import PDFDocumentChunker
from services.ai.summarisation.summariser import DocumentSummarizer
from services.ai.embedding.embedder import Embedder

from general.decorators import retry_with_backoff

from .models.logs import ProcessingLog, EventEnum

from django.conf import settings

from django.db import transaction
from document_manager.models import Document
from django.shortcuts import get_object_or_404

from openai import OpenAI

import logging
logger = logging.getLogger(__name__)

'''
Control class to orchestrate the whole document handling from upload to chat-ready.

The flow:
    1) chunk the document into:
        - sentances
        - paragraphs
        - pages
        - 6 pages
    2) summarise the 6 page summaries and create a headline
    3) create a contents page from the headlines
    4) use the headlines to order the doc into thematic sections
    5) summarise the sections using 6 page summaries
    6) delete the 6 page summaries
    7) summarise the document using the section summaries
    8) embed all of the below.

Content that gets embedded:
    - Every sentance
    - Every paragraph
    - Every page
    - Every 6 pages
    - Contents page using 6 page summarised headlines
    - Section summaries
    - Document summary
'''
class Control:

    def __init__(self):
        self.chunking_model = "gpt-4.1-2025-04-14"
        self.summarisation_model = "gpt-4.1-2025-04-14"
        self.embedding_model = "text-embedding-3-small" 
        self.llm_service = OpenAI(api_key=settings.OPENAI_API_KEY)

    def process_document(self, document:Document) -> bool:
        if not self._validate_document(document):
            logger.error("Document not valid.")
            return False
        
        ProcessingLog.create_log(document, EventEnum.VALIDATION_COMPLETED)
        ProcessingLog.create_log(document, EventEnum.PROCESSING_STARTED)

        self._update_processing_status(document, 'processing')

        try:
            # Chunk and summarize in one transaction
            with transaction.atomic():
                self.chunk_document(document)
                self.conduct_summarisations(document)

            # Embed separately - if this fails, we keep chunks/summaries
            self.embed_document(document)

            self._update_processing_status(document, 'completed')
            return True
        except Exception as e:
            logger.error('Failed to process document in control pipeline | Error: ', e)
            self._update_processing_status(document, 'failed')
            return False

    def _validate_document(self, document:Document) -> bool:
        '''Validate document before processing it.'''
        if not Document.objects.filter(pk=document.id).exists():
            return False

        if document.processing_status not in ['pending', 'failed']:
            logger.error("Document processing_status is not pending or failed.")
            return False
        
        if not document.file:
            raise ValueError("Document has no file attached")
        
        if not document.file.name.endswith('.pdf'):
            raise ValueError("Only PDF documents are supported")
        
        return True
        
    def _update_processing_status(self, document:Document, status:str) -> None:
        if not document:
            raise ValueError("No document given.")
        if not status:
            raise ValueError("No status update given.")
        
        old_status = document.processing_status
        document.processing_status = status
        document.save(update_fields=['processing_status'])
        
        # Log status changes
        logger.info(f"Document {document.id} status: {old_status} → {status}")
        
    @retry_with_backoff
    def chunk_document(self, document:Document):
        try:
            ProcessingLog.create_log(document, EventEnum.CHUNKING_STARTED)
            chunker = PDFDocumentChunker(document=document, llm_service=self.llm_service, chunking_model=self.chunking_model)
            chunker.process_document()
            ProcessingLog.create_log(document, EventEnum.CHUNKING_COMPLETED)
        except Exception as e:
            logger.error(f"Failed to chunk document | Error: {e}", exc_info=True, extra={
                'document_id': document.id,
                'document_name': document.name,
                'stage': 'chunking'
            })
            ProcessingLog.create_log(document, EventEnum.CHUNKING_FAILED)
            raise

    @retry_with_backoff
    def conduct_summarisations(self, document:Document):
        try:
            ProcessingLog.create_log(document, EventEnum.SUMMARISATION_STARTED)
            summariser = DocumentSummarizer(document_instance=document, llm_service=self.llm_service, model=self.summarisation_model)
            summariser.process_document()
            ProcessingLog.create_log(document, EventEnum.SUMMARISATION_COMPLETED)
        except Exception as e:
            logger.error(f"Failed to conduct summarisations | Error: {e}", exc_info=True, extra={
                'document_id': document.id,
                'document_name': document.name,
                'stage': 'summarisation'
            })
            ProcessingLog.create_log(document, EventEnum.SUMMARISATION_FAILED)
            raise

    @retry_with_backoff
    def embed_document(self, document:Document):
        try:
            ProcessingLog.create_log(document, EventEnum.EMBEDDING_STARTED)
            embedder = Embedder(self.llm_service, self.embedding_model)
            embedder.process_document(document)
            ProcessingLog.create_log(document, EventEnum.EMBEDDING_COMPLETED)
        except Exception as e:
            logger.error(f"Failed to embed document chunks and summaries, and save the embeddings. | Error: {e}", exc_info=True, extra={
                'document_id': document.id,
                'document_name': document.name,
                'stage': 'embedding'
            })
            ProcessingLog.create_log(document, EventEnum.EMBEDDING_FAILED)
            raise