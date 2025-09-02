from django.shortcuts import render, get_object_or_404

from .models import Document


def document_library(request):
    documents = Document.objects.filter(is_active=True)

    context={"documents":documents}
    return render(request, "document_library.html", context)

def documents(request):
    # This is set up for the fancy document page with rankings of popularity etc etc
    context={}
    return render(request, "documents.html", context)

