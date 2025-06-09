from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import ListView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from .models import RequestedDocument
from .forms import RequestDocumentForm, VoteDocumentForm

# Create your views here.

def voting_view(request):
    all_requested_documents = RequestedDocument.objects.all()
    request_form = RequestDocumentForm
    context={"all_requested_documents":all_requested_documents, "request_form":request_form}
    return render(request, 'voting.html', context)

@require_POST
def request_document(request):
    """AJAX handler for document request form submission."""
    form = RequestDocumentForm(request.POST)
    
    if form.is_valid():
        # Create a new document request
        document_name = form.cleaned_data['document_name']
        document_url = form.cleaned_data['document_url']
        
        # Save the document request
        document = RequestedDocument.objects.create(
            document_name=document_name,
            document_url=document_url,
            # If you're tracking who requested it:
            # requested_by=request.user if request.user.is_authenticated else None
        )
        
        return JsonResponse({
            'status': 'success',
            'document_id': document.id,
            'document_name': document.document_name
        })
    else:
        # Return form errors for display
        return JsonResponse({
            'status': 'error',
            'errors': form.errors
        })


@login_required
@require_POST
def vote_document(request):
    """AJAX handler for document voting."""
    form = VoteDocumentForm(request.POST)
    
    if form.is_valid():
        document_id = form.cleaned_data['document_id']
        
        try:
            document = RequestedDocument.objects.get(id=document_id)
            
            # Record the vote
            document.votes += 1
            document.save()
            
            return JsonResponse({
                'status': 'success',
                'votes': document.votes
            })
            
        except RequestedDocument.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Document not found'
            })
    else:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid request'
        })