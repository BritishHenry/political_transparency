"""
URL configuration for political_transparency project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from general import views as g_views
from document_manager import views as docs_views
from donations_manager import views as dons_views
from voting_manager import views as vote_views
from chat_manager import views as chat_views

urlpatterns = [
    path("admin/",          admin.site.urls),

    # Auxilliary Pages 
    path("",                    g_views.home, name="home"),
    path("about/",              g_views.about, name="about"),
    path("contact/",            g_views.contact, name="contact"),
    path("terms-of-use/",       g_views.terms_of_use, name="terms_of_use"),
    path("privacy-policy/",     g_views.privacy_policy, name="privacy_policy"),

    # Donations
    path("donations/",              dons_views.donations_view, name="donations"),

    # Voting for new docs
    #path("voting/",                     vote_views.voting_view, name="voting"),
    #path("voting/vote-document/",        vote_views.vote_document, name="vote_document"),
    #path("voting/request-document/",     vote_views.request_document, name="request_document"),

    # Document Handling
    path("document-library/",       docs_views.document_library, name="document_library"),
    #path("documents/",              docs_views.documents, name="documents"),
    path("documents/<slug:slug>/",  chat_views.ChatView.as_view(), name="chat_view"),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

