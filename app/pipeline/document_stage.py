import os
import logging
from markitdown import MarkItDown

logger = logging.getLogger(__name__)

def extract_text(file_path: str) -> str:

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return ""
        
    try:
        md = MarkItDown()
        result = md.convert(file_path)
        return result.text_content
    except Exception as e:
        logger.error(f"Failed to parse document {file_path}: {e}")
        return ""
