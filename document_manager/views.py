from django.shortcuts import render

# Create your views here.

def document_library(request):
    context={}
    return render(request, "document_library.html", context)

def documents(request):
    context={}
    return render(request, "documents.html", context)

def chat(request):
    context={}
    return render(request, "chat.html", context)
