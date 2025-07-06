'''

This file will be used to orchestrate the whole document handling process, from upload to chat-ready.

Methods should be imported into here from across the app to manage the whole pipeline efficiently and in one place.

This can also be used as a single source of truth for any key variables.

'''

from services.ai.chunking.chunker import PDFDocumentChunker
from services.ai.summarisation.summariser import DocumentSummarizer
from services.ai.embedding.embedder import Embedder

from general.decorators import retry_with_backoff
from .utils import validate_document, update_processing_status

from document_manager.models.logs import ProcessingLog, EventEnum

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
        logger.info('Control.process_document() triggered inside document_manager/pipeline.py')
        if not validate_document(document):
            logger.error("Document not valid.")
            return False
        
        ProcessingLog.create_log(document, EventEnum.VALIDATION_COMPLETED)
        ProcessingLog.create_log(document, EventEnum.PROCESSING_STARTED)

        update_processing_status(document, 'processing')

        try:
            # Chunk and summarize in one transaction
            chunker = self.chunk_document(document)
            summariser = self.conduct_summarisations(document)
            embedder, data_to_save, qdrant_client, collection_name= self.embed_document(document)

            with transaction.atomic():
                self._save_chunks_to_database(chunker)
                self._save_summaries_to_database(summariser)
                self._save_embeddings(embedder, data_to_save, qdrant_client, collection_name) 
                        
            update_processing_status(document, 'completed')
            document.is_active = True
            document.save(update_fields=['is_active'])
            return True
        except Exception as e:
            logger.error('Failed to process document in control pipeline | Error: ', e)
            update_processing_status(document, 'failed')
            return False

    ### CHUNKING 

    # @retry_with_backoff() - removing to avoid repeat retries of expensive errors
    def chunk_document(self, document:Document):
        try:
            ProcessingLog.create_log(document, EventEnum.CHUNKING_STARTED)
            chunker = PDFDocumentChunker(document=document, llm_service=self.llm_service, chunking_model=self.chunking_model)
            chunker.process_document()
            ProcessingLog.create_log(document, EventEnum.CHUNKING_COMPLETED)
            return chunker
        except Exception as e:
            logger.error(f"Failed to chunk document | Error: {e}", exc_info=True, extra={
                'document_id': document.id,
                'document_name': document.name,
                'stage': 'chunking'
            })
            ProcessingLog.create_log(document, EventEnum.CHUNKING_FAILED)
            raise
    
    @retry_with_backoff(max_retries=5) # Only retries the saving, rather than the whole expensive chunking process
    def _save_chunks_to_database(self, chunker):
        logger.info("Saving chunks to database")
        return chunker.save_chunks_to_database() 

    ### SUMMARISATION

    #@retry_with_backoff()
    def conduct_summarisations(self, document:Document):
        try:
            ProcessingLog.create_log(document, EventEnum.SUMMARISATION_STARTED)
            summariser = DocumentSummarizer(document_instance=document, llm_service=self.llm_service, model=self.summarisation_model)
            summariser.process_document()
            ProcessingLog.create_log(document, EventEnum.SUMMARISATION_COMPLETED)
            return summariser
        except Exception as e:
            logger.error(f"Failed to conduct summarisations | Error: {e}", exc_info=True, extra={
                'document_id': document.id,
                'document_name': document.name,
                'stage': 'summarisation'
            })
            ProcessingLog.create_log(document, EventEnum.SUMMARISATION_FAILED)
            raise

    @retry_with_backoff(max_retries=5) # Only retries the saving, rather than the whole summarisation process
    def _save_summaries_to_database(self, summariser):
        logger.info("Saving sumaries to database")
        return summariser._save_results_to_database() 

    ### EMBEDDING
    #@retry_with_backoff()
    def embed_document(self, document:Document):
        try:
            ProcessingLog.create_log(document, EventEnum.EMBEDDING_STARTED)
            embedder = Embedder(self.llm_service, self.embedding_model)
            data_to_save, qdrant_client, collection_name = embedder.process_document(document)
            ProcessingLog.create_log(document, EventEnum.EMBEDDING_COMPLETED)
            return embedder, data_to_save, qdrant_client, collection_name
        except Exception as e:
            logger.error(f"Failed to embed document chunks and summaries, and save the embeddings. | Error: {e}", exc_info=True, extra={
                'document_id': document.id,
                'document_name': document.name,
                'stage': 'embedding'
            })
            ProcessingLog.create_log(document, EventEnum.EMBEDDING_FAILED)
            raise
    
    @retry_with_backoff(max_retries=5) # Only retries the saving, rather than the whole summarisation process
    def _save_embeddings(self, embedder, data_to_save, qdrant_client, collection_name):
        logger.info("Saving embeddings to vector database and references to postgre")
        return embedder._save_results_to_database(data_to_save, qdrant_client, collection_name) 