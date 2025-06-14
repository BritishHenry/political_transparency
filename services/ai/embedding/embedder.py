'''
This file will handle the embedding of all the document's chunks
'''

class Embedder:
    def __init__(self, document, llm_service, embedding_model):
        self.document = document
        self.llm_service = llm_service
        self.embedding_model = embedding_model

    def _get_embedding(self, input):
        response = self.llm_service.embeddings.create(
            input=input,
            model=self.embedding_model
        )
        return response.data[0].embedding

    def _save_embeddings_to_vector_database(self, embedding):
        pass

    def _save_vector_id(self):
        pass
        

    def process_document(self):
        from apps.document_manager.models import DocumentChunk, DocumentSummary

        chunks =    DocumentChunk.objects.filter(document=self.document)
        summaries = DocumentSummary.objects.filter(document=self.document)

        # I was extratcing the content form the querysets into lists for easier management, 
        # but I want to keep it in queryset now as it will make updating the chunks eaiser with their vector id etc

        if chunks:
            for chunk in chunks:
                embedding = self._get_embedding(chunk.content)
        

        if summaries:
            for summary in summaries:
                embedding = self._get_embedding(summary.content)