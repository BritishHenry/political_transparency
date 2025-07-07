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
from document_manager.models.chunks import DocumentChunk
from document_manager.models.summaries import DocumentSummary

from django.conf import settings

from django.db import transaction
from document_manager.models.general import Document 
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

    def __init__(self, document:Document):
        self.chunking_model = "gpt-4.1-2025-04-14"
        self.summarisation_model = "gpt-4.1-2025-04-14"
        self.embedding_model = "text-embedding-3-small" 
        self.llm_service = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.document = document

    def process_document(self) -> bool:
        logger.info('Control.process_document() triggered inside document_manager/pipeline.py')
        if not validate_document(self.document):
            logger.error("Document not valid.")
            return False
        

        
        ProcessingLog.create_log(self.document, EventEnum.VALIDATION_COMPLETED)
        ProcessingLog.create_log(self.document, EventEnum.PROCESSING_STARTED)
        update_processing_status(self.document, 'processing')

        try:
            # Chunk and and save chunks
            logger.info("Chunking document now.")
            chunker = self.chunk_document(self.document)
            if chunker:
                logger.info("DocumentChunks processed -> next is to save them.")
                self._save_chunks_to_database(chunker)
                logger.info("Chunks saved.")
            else:
                logger.info("chunker is None -> chunks were not processed.")

            logger.info("Summarising chunks now.")
            summariser = self.conduct_summarisations(self.document)
            if summariser:
                logger.info("Summaries created -> next is to save them.")
                self._save_summaries_to_database(summariser)
                logger.info("Summaries saved.")
            else:
                logger.info("summariser is None -> summaries were not processed.")
            
            # Currently not adding a check if embeddings are already saved as this is the last step so it would be redundant. Also causes lots of additional work.
            logger.info("Embedding chunks and summaries now.")
            embedder = self.embed_document(self.document)
            logger.info("Embedding completed -> next is to save them.")
            self._save_embeddings(embedder) 
            logger.info("Embeddings saved -> Pipeline complete.")
                        
            update_processing_status(self.document, 'completed')
            self.document.is_active = True
            self.document.save(update_fields=['is_active'])
            return True
        
        except Exception as e:
            logger.error('Failed to process document in control pipeline | Error: ', e)
            update_processing_status(self.document, 'failed')
            return False

    ### CHUNKING 

    # @retry_with_backoff() - removing to avoid repeat retries of expensive errors
    def chunk_document(self):
        if DocumentChunk.objects.filter(document=self.document).exists():
            logger.info('Chunking already complete')
            return
        
        try:
            ProcessingLog.create_log(self.document, EventEnum.CHUNKING_STARTED)

            chunker = PDFDocumentChunker(document=self.document, llm_service=self.llm_service, chunking_model=self.chunking_model)
            chunker.process_document()
            
            ProcessingLog.create_log(self.document, EventEnum.CHUNKING_COMPLETED)
            return chunker
        
        except Exception as e:
            logger.error(f"Failed to chunk document | Error: {e}", exc_info=True, extra={
                'document_id': self.document.id,
                'document_name': self.document.name,
                'stage': 'chunking'
            })
            ProcessingLog.create_log(self.document, EventEnum.CHUNKING_FAILED)
            raise
    
    @retry_with_backoff(max_retries=5) # Only retries the saving, rather than the whole expensive chunking process
    def _save_chunks_to_database(self, chunker):
        logger.info("Saving chunks to database")
        return chunker.save_chunks_to_database() 

    ### SUMMARISATION

    #@retry_with_backoff()
    def conduct_summarisations(self):
        if DocumentSummary.objects.filter(document=self.document).exists():
            logger.info('Summaries already complete')
            return
        
        try:
            ProcessingLog.create_log(self.document, EventEnum.SUMMARISATION_STARTED)
            
            summariser = DocumentSummarizer(document_instance=self.document, llm_service=self.llm_service, model=self.summarisation_model)
            summariser.process_document()

            ProcessingLog.create_log(self.document, EventEnum.SUMMARISATION_COMPLETED)
            return summariser
        
        except Exception as e:
            logger.error(f"Failed to conduct summarisations | Error: {e}", exc_info=True, extra={
                'document_id': self.document.id,
                'document_name': self.document.name,
                'stage': 'summarisation'
            })
            ProcessingLog.create_log(self.document, EventEnum.SUMMARISATION_FAILED)
            raise

    @retry_with_backoff(max_retries=5) # Only retries the saving, rather than the whole summarisation process
    def _save_summaries_to_database(self, summariser):
        logger.info("Saving sumaries to database")
        return summariser._save_results_to_database() 

    ### EMBEDDING
    #@retry_with_backoff()
    def embed_document(self):
        try:
            ProcessingLog.create_log(self.document, EventEnum.EMBEDDING_STARTED)
            embedder = Embedder(self.document, self.llm_service, self.embedding_model)
            embedder.process_document()
            ProcessingLog.create_log(self.document, EventEnum.EMBEDDING_COMPLETED)
            return embedder
        except Exception as e:
            logger.error(f"Failed to embed document chunks and summaries, and save the embeddings. | Error: {e}", exc_info=True, extra={
                'document_id': self.document.id,
                'document_name': self.document.name,
                'stage': 'embedding'
            })
            ProcessingLog.create_log(self.document, EventEnum.EMBEDDING_FAILED)
            raise
    
    @retry_with_backoff(max_retries=5) # Only retries the saving, rather than the whole summarisation process
    def _save_embeddings(self, embedder):
        logger.info("Saving embeddings to vector database and references to postgre")
        return embedder._save()

    ### COST ESTIMATION

    def estimate_document_processing_cost(self):
        '''
        Here, I need to write a method to estimate the cost of full document processing pipeline.
        Includes input and output of:
            - chunking 
            - summarising
            - embedding 

        For chunking: 
            - Create a token estimate for page inputs.
            - Create a token estimate for sentance and paragraph (only these use llms) outputs
            - query the databse for sentances and paragraph chunk types. 
                - (Only sentances and paragrpahs use an llm for chunking -> pages and 6 pages are standard python/pdfplumber.)
            - for each type: (len(queryset) * input_token_cost) + (len(queryset) * output_token_cost)
            - Add all type estimations together.

        For summarisation:
            - Same as chunking, but with summaries

        For Embeddings:
            - query for all chunks and summaries
            - len(queryset) * embedding_token_cost

        Finally:
            - Add all 3 totals together

        !! Once complete, add to the Document model:
            - estimated_cost_of_processing=models.FloatField
            - chunking model
            - summarising model
            - embedding model
        '''

        # OpenAI's tokenizer to estimate tokens: https://platform.openai.com/tokenizer

        from document_manager.models.summaries import DocumentSummary

        num_summaries = DocumentSummary.objects.filter(document=self.document, summary_type='section').count()
        num_pages =     DocumentChunk.objects.filter(document=self.document, chunk_type='page').count()
        num_six_pages = DocumentChunk.objects.filter(document=self.document, chunk_type='6_page').count()

        input_model_price_map = { 
            "gpt-4.1-2025-04-14": {
                "cost":2, # USD per 1 million tokens
                "tokenizer":"cl100k_base",
                "estimated_tokens":{
                    "page":250,
                    "six_page": 1500, 
                    "six_page_and_headline":1550, # Used to generate six page summary
                    "six_page_headlines": 650, # Used to get thematic sections -> becomes contents page in Document model
                    "six_page_summaries_and_section_headline": ((150*(0.4*num_summaries))+10), # Used to create section summary. calculation is a large approximation: 150 is approx six page summary tokens, 0.4 is cause theres approx 40% the num of sections as there are num of headlines/summaries, +10 is the approx tokens for a headline.
                    "all_sections":(340*num_summaries), # Used to create document summary
                }
            }
        }

        output_model_price_map = {
            "gpt-4.1-2025-04-14":  {
                "cost":8, # USD per 1 million tokens
                "tokenizer":"cl100k_base",
                "estimated_tokens":{
                    "sentence_and_paragraphs":250, # Making estimation that this will be equal to page tokens due to processing method. sentances&paragraphs outputted from the same call. page -> extract sentences and paragraphs.
                    "six_page_summary": 340,
                    "six_page_headlines": 650,
                    "section_identification":750, # Assuming this is slightly above to the six_page_headline as it just takes that as input and reformats it in json. never store this so difficult to be sure.
                    "section_summary": 340,
                    "document_summary":250,

                }
            }
        }

        # Add logic to calculate the total tokens for each input
        # Multiply total tokens by the cost per million

        # Add logic to calculate the total tokens for each ouput
        # Multiply total tokens by the cost per million


        embedding_model_price_map = { # USD per 1 million tokens
            "text-embedding-3-small" :  {
                "cost":0.02,
                "tokenizer":"cl100k_base"
            }
        }

        # Add logic to estimate the embedding cost
        # Need to figure out everything that gets embedded
        # Get the number of tokens
        # multiply by the cost per million 

        # Finally, add it all together
        # Finally, finally, multiply by 1.2 to get an upper bound to account for mistakes and system messgaes etc
            # Accuracy is not super important as the total cost will always be small. These are estimations.
