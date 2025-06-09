from django import forms
from .validators import validate_document_name, validate_document_url
from .models import RequestedDocument

class RequestDocumentForm(forms.Form):
    """
    Form for users to request a new document to be added to the platform.
    Includes security validators to protect against malicious content.
    """
    document_name = forms.CharField(
        max_length=RequestedDocument.MAX_NAME_LENGTH,  # Reference the model constant
        required=True,
        validators=[validate_document_name],
        widget=forms.TextInput(
            attrs={
                'class': 'form-input',
                'placeholder': 'Enter document name or description',
                'aria-label': 'Document name or description',
            }
        )
    )
    
    document_url = forms.URLField(
        required=False,
        validators=[validate_document_url],
        widget=forms.URLInput(
            attrs={
                'class': 'form-input',
                'placeholder': 'Optional: Link to the document',
                'aria-label': 'Document URL',
            }
        )
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""  # Removes the colon after form labels


class VoteDocumentForm(forms.Form):
    """
    Form for users to vote for a document suggestion.
    This is a minimal form that primarily serves as a way to handle the vote action.
    The actual vote button will be styled with CSS and implemented in the template.
    """
    document_id = forms.IntegerField(
        widget=forms.HiddenInput()
    )
    
    def __init__(self, *args, **kwargs):
        document_id = kwargs.pop('document_id', None)
        super().__init__(*args, **kwargs)
        
        if document_id:
            self.fields['document_id'].initial = document_id