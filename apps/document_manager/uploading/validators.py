import os
import magic
import zipfile
import tempfile
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PyPDF2 import PdfReader


# Safe file extensions
ALLOWED_EXTENSIONS = {
    # Documents
    'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt',
    # Spreadsheets
    'xls', 'xlsx', 'csv', 'ods',
    # Presentations
    'ppt', 'pptx', 'odp',
    # Images (if needed for document processing)
    'jpg', 'jpeg', 'png', 'gif',
    # Other
    'md', 'json', 'xml'
}

# Mime types that are considered safe
ALLOWED_MIME_TYPES = {
    # Documents
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'application/rtf',
    'application/vnd.oasis.opendocument.text',
    # Spreadsheets
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv',
    'application/vnd.oasis.opendocument.spreadsheet',
    # Presentations
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.oasis.opendocument.presentation',
    # Images
    'image/jpeg',
    'image/png',
    'image/gif',
    # Other
    'text/markdown',
    'application/json',
    'application/xml',
    'text/xml'
}

# Known malicious file signatures
MALICIOUS_SIGNATURES = [
    b'MZ',  # Windows executable
    b'\x7fELF',  # Linux executable
    b'#!/bin/sh',  # Shell script
    b'#!/bin/bash',  # Bash script
    b'<?php',  # PHP script
    b'<script',  # JavaScript
    b'<%',  # ASP/JSP
]

# Maximum file size (in bytes)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def validate_file_extension(file):
    """Validate file extension is allowed"""
    ext = os.path.splitext(file.name)[1][1:].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            _('File type not allowed. Allowed types: %(allowed)s'),
            params={'allowed': ', '.join(ALLOWED_EXTENSIONS)},
        )


def validate_file_size(file):
    """Validate file size is within limits"""
    if file.size > MAX_FILE_SIZE:
        raise ValidationError(
            _('File size exceeds maximum limit of %(max_size)s MB'),
            params={'max_size': MAX_FILE_SIZE // (1024 * 1024)},
        )


def validate_mime_type(file):
    """Validate MIME type is allowed"""
    file.seek(0)
    file_mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)
    
    if file_mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            _('File MIME type %(mime)s is not allowed'),
            params={'mime': file_mime},
        )


def check_malicious_content(file):
    """Check for known malicious signatures"""
    file.seek(0)
    header = file.read(1024)  # Read first 1KB
    file.seek(0)
    
    for signature in MALICIOUS_SIGNATURES:
        if signature in header:
            raise ValidationError(
                _('File contains potentially malicious content')
            )


def validate_pdf_safety(file):
    """Specific validation for PDF files"""
    if not file.name.lower().endswith('.pdf'):
        return  # Skip if not PDF
    
    try:
        file.seek(0)
        pdf = PdfReader(file)
        
        # Check for JavaScript
        if '/JS' in pdf.trailer:
            raise ValidationError(_('PDF contains JavaScript which is not allowed'))
        
        # Check for embedded files
        if '/EmbeddedFiles' in pdf.trailer:
            raise ValidationError(_('PDF contains embedded files which are not allowed'))
        
        # Check for suspicious actions
        for page in pdf.pages:
            if '/AA' in page or '/OpenAction' in page:
                raise ValidationError(_('PDF contains automatic actions which are not allowed'))
                
    except Exception as e:
        raise ValidationError(_('Invalid or corrupted PDF file: %(error)s'), params={'error': str(e)})
    finally:
        file.seek(0)


def check_zip_bomb(file):
    """Check if file is a potential zip bomb"""
    if not file.name.lower().endswith(('.zip', '.docx', '.xlsx', '.pptx')):
        return  # Skip if not a zip-based file
    
    try:
        file.seek(0)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file.read())
            tmp.flush()
            
            with zipfile.ZipFile(tmp.name, 'r') as zf:
                total_uncompressed = sum(zinfo.file_size for zinfo in zf.infolist())
                total_compressed = sum(zinfo.compress_size for zinfo in zf.infolist())
                
                # If compression ratio is too high, it might be a zip bomb
                if total_compressed > 0 and total_uncompressed / total_compressed > 100:
                    raise ValidationError(_('File has suspicious compression ratio, possible zip bomb'))
                
                # Check total uncompressed size
                if total_uncompressed > MAX_FILE_SIZE * 10:  # 10x max file size
                    raise ValidationError(_('Uncompressed file size too large'))
                    
    except zipfile.BadZipFile:
        pass  # Not a zip file, which is fine
    except Exception as e:
        raise ValidationError(_('Error checking file compression: %(error)s'), params={'error': str(e)})
    finally:
        file.seek(0)
        if 'tmp' in locals() and os.path.exists(tmp.name):
            os.unlink(tmp.name)


def validate_file_safety(file):
    """Main validation function that runs all checks"""
    validate_file_extension(file)
    validate_file_size(file)
    validate_mime_type(file)
    check_malicious_content(file)
    validate_pdf_safety(file)
    check_zip_bomb(file)


def safe_file_name(filename):
    """Sanitize filename to prevent directory traversal and other issues"""
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove potentially dangerous characters
    safe_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- '
    filename = ''.join(c for c in filename if c in safe_chars)
    
    # Ensure filename has an extension
    if '.' not in filename:
        filename += '.unknown'
    
    return filename


def generate_safe_filename(instance, filename):
    """Generate a safe filename with UUID to prevent overwrites"""
    import uuid
    from datetime import datetime
    
    safe_name = safe_file_name(filename)
    name, ext = os.path.splitext(safe_name)
    
    # Add UUID to prevent filename collisions
    unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
    
    # Use the document's date field if available, otherwise use current date
    if hasattr(instance, 'date') and instance.date:
        file_date = instance.date
    else:
        file_date = datetime.now().date()
    
    # Add year/month directory structure based on document date
    return f"documents/{file_date.year}/{file_date.month:02d}/{unique_filename}"


# Utility function to use with Django model
def validate_document_file(file):
    """Combined validator for Django FileField"""
    try:
        validate_file_safety(file)
    except ValidationError as e:
        # Log the validation error for security monitoring
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"File validation failed: {file.name} - {str(e)}")
        raise e
