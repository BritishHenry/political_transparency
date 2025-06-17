'''

This file will be used to orchestrate the whole document handling process, from upload to chat-ready.

Methods should be imported into here from across the app to manage the whole pipeline efficiently and in one place.

This can also be used as a single source of truth for any key variables.

'''
from django.shortcuts import get_object_or_404

from services.ai.chunking.utils import upload_file_to_openai, get_document_structure, get_document_chunks, save_chunks


from services.ai.chunking.chunker import PDFDocumentChunker
from services.ai.summarisation.summariser import DocumentSummarizer
from services.ai.embedding.embedder import Embedder

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
        self.chunking_model = "gpt-4.1"
        self.summarisation_model = ""
        self.embedding_model = "text-embedding-3-small" 
        self.llm_service = OpenAI()

    def chunk_document(self, document):
        try:
            chunker = PDFDocumentChunker(document=document, llm_service=self.llm_service, chunking_model=self.chunking_model)
            chunker.process_document()
        except Exception as e:
            logger.error("Failed to chunk document | Error msg: ", e)
            raise
    
    def conduct_summarisations(self, document):
        try:
            summariser = DocumentSummarizer(document_instance=document, llm_service=self.llm_service, model=self.summarisation_model)
            summariser.process_document()
        except Exception as e:
            logger.error("Failed to conduct summarisations | Error msg: ", e)
            raise

    def embed_document(self, document):
        try:
            embedder = Embedder(self.llm_service, self.embedding_model)
            embedder.process_document(document)
        except Exception as e:
            logger.error("Failed to embed document chunks and summaries. | Error msg: ", e)