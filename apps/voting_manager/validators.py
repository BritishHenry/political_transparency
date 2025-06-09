import re
from urllib.parse import urlparse
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
import requests


def validate_document_name(value):
    """
    Validates document names to prevent potential XSS or injection attacks.
    
    Args:
        value: The document name string to validate
        
    Raises:
        ValidationError: If the document name contains potentially harmful content
    """
    # Note: Max length is enforced by the model and form field definition
    # This validator focuses on content security
    
    # Check for potentially malicious script tags or injection patterns
    script_pattern = re.compile(r'<.*?(script|iframe|object|embed|on\w+\s*=)', re.IGNORECASE)
    if script_pattern.search(value):
        raise ValidationError("Document name contains potentially unsafe content.")
    
    # Check for excessive special characters that might indicate an attack
    special_char_pattern = re.compile(r'[<>{}()\[\]\'"`&;:|\\]')
    special_chars = special_char_pattern.findall(value)
    if len(special_chars) > 5:  # Allow some special characters, but not too many
        raise ValidationError("Document name contains too many special characters.")
    
    # Check for common SQL injection patterns
    sql_pattern = re.compile(r'\b(select|insert|update|delete|drop|alter|exec|union)\b', re.IGNORECASE)
    if sql_pattern.search(value):
        raise ValidationError("Document name contains prohibited keywords.")
    
    return value


def validate_document_url(url):
    """
    Validates document URLs to ensure they are safe and from trusted sources.
    
    Args:
        url: The URL string to validate
        
    Raises:
        ValidationError: If the URL seems unsafe or suspicious
    """
    # Skip validation if URL is empty (since it's optional in the form)
    if not url:
        return url
    
    # Use Django's URLValidator first
    url_validator = URLValidator()
    try:
        url_validator(url)
    except ValidationError:
        raise ValidationError("Please enter a valid URL.")
    
    # Parse the URL to examine its components
    parsed_url = urlparse(url)
    
    # Ensure the URL uses HTTPS
    if parsed_url.scheme != 'https':
        raise ValidationError("Only HTTPS URLs are accepted for security reasons.")
    
    # Check against known file types that might be harmful
    file_extensions = ['.exe', '.dll', '.bat', '.cmd', '.sh', '.jar', '.js', '.vbs']
    if any(parsed_url.path.lower().endswith(ext) for ext in file_extensions):
        raise ValidationError("URLs to executable files are not allowed.")
    
    # Block URLs with suspicious patterns (e.g., many subdomains, numeric IPs)
    domain_parts = parsed_url.netloc.split('.')
    
    # Check for IP address URLs
    ip_pattern = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
    if ip_pattern.match(parsed_url.netloc):
        raise ValidationError("URLs with IP addresses are not allowed.")
    
    # Check for too many subdomains (potential for phishing/malicious sites)
    if len(domain_parts) > 5:
        raise ValidationError("URL has too many subdomains and may be suspicious.")
    
    # Check for unusual port numbers
    if parsed_url.port and parsed_url.port not in (80, 443):
        raise ValidationError("URLs with non-standard ports are not allowed.")
    
    # Check for Unicode character abuse (homograph attacks)
    try:
        idna_netloc = parsed_url.netloc.encode('idna').decode('ascii')
        if idna_netloc != parsed_url.netloc and not all(ord(c) < 128 for c in parsed_url.netloc):
            raise ValidationError("URL contains potentially misleading Unicode characters.")
    except UnicodeError:
        raise ValidationError("URL contains invalid Unicode characters.")
    
    return url


def validate_url_is_accessible(url):
    """
    Validates that a URL is accessible and returns proper content.
    NOTE: This validator should be used sparingly due to the external request.
    Consider implementing with a task queue for production.
    
    Args:
        url: The URL to validate
        
    Raises:
        ValidationError: If the URL cannot be accessed or returns an error
    """
    # Skip validation if URL is empty
    if not url:
        return url
    
    try:
        # Only make a HEAD request to avoid downloading large content
        response = requests.head(
            url, 
            timeout=5,
            headers={'User-Agent': 'PoliticalDocumentAI Validator/1.0'},
            allow_redirects=True
        )
        
        # Check if the response is successful (only accept 2xx status codes)
        if not 200 <= response.status_code < 300:
            raise ValidationError(f"The URL returned an error (status code: {response.status_code}).")
        
        # Check content type if available
        content_type = response.headers.get('Content-Type', '')
        
        # Specifically reject JSON content
        if 'application/json' in content_type:
            raise ValidationError("JSON files are not supported. Please provide a document in HTML, PDF, or document format.")
        
        # Define valid content types for political documents
        valid_types = [
            'text/html',           # HTML pages
            'text/plain',          # Plain text
            'application/pdf',     # PDF documents
            'application/msword',  # MS Word
            'application/vnd.openxmlformats-officedocument'  # Modern Office formats
        ]
        
        if not any(valid_type in content_type for valid_type in valid_types):
            raise ValidationError("The URL does not appear to contain valid document content. Supported formats include HTML, PDF, and document files.")
            
    except requests.RequestException as e:
        raise ValidationError(f"Could not access the URL: {str(e)}")
    
    return url