import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=3, base_delay=1, max_delay=60, 
                      retry_on=None, exclude=None):
    """
    Decorator for exponential backoff retry logic
    
    Args:
        retry_on: Tuple of exception types to retry on. If None, retries all.
        exclude: Tuple of exception types to never retry on.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Check if we should retry this exception
                    if exclude and isinstance(e, exclude):
                        logger.error(f"Non-retryable exception: {type(e).__name__}: {e}")
                        raise
                    
                    if retry_on and not isinstance(e, retry_on):
                        logger.error(f"Exception not in retry list: {type(e).__name__}: {e}")
                        raise
                    
                    if attempt == max_retries:
                        logger.error(f"Final attempt failed after {max_retries} retries: {e}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed: "
                        f"{type(e).__name__}: {e}. Retrying in {delay}s..."
                    )
                    time.sleep(delay)
            
        return wrapper
    return decorator