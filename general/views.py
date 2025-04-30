from django.shortcuts import render

# Create your views here.

def home(request):
    context={}
    return render(request, "home.html", context)

def about(request):
    context={}
    return render(request, "about.html", context)

def contact(request):
    context={}
    return render(request, "contact.html", context)

def privacy_policy(request):
    context={}
    return render(request, "privacy_policy.html", context)

def terms_of_use(request):
    context={}
    return render(request, "terms_of_use.html", context)
