import os
import logging
import numpy as np
from markitdown import MarkItDown

logger = logging.getLogger(__name__)

# ponytail: lazy singleton — EasyOCR takes ~3s to load, only pay that cost once
_ocr_reader = None

def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        import torch
        _ocr_reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available())
        logger.info("EasyOCR reader loaded (gpu=%s)", torch.cuda.is_available())
    return _ocr_reader


def _ocr_image(file_path: str) -> str:
    """Run EasyOCR on an image file."""
    try:
        reader = _get_ocr_reader()
        return '\n'.join(reader.readtext(file_path, detail=0))
    except Exception as e:
        logger.error("EasyOCR image failed: %s", e)
        return ""


def _ocr_pdf(file_path: str) -> str:
    """Convert each PDF page to an image via pymupdf, then run EasyOCR."""
    try:
        import fitz
        reader = _get_ocr_reader()
        doc = fitz.open(file_path)
        pages_text = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = img[:, :, :3]
            result = reader.readtext(img, detail=0)
            if result:
                pages_text.append('\n'.join(result))
        doc.close()
        return '\n\n'.join(pages_text)
    except Exception as e:
        logger.error("EasyOCR PDF failed: %s", e)
        return ""


_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}


def extract_text(file_path: str) -> str:
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        return ""

    # 1. Try MarkItDown — handles DOCX, XLSX, PPTX, text-based PDFs
    try:
        result = MarkItDown().convert(file_path)
        text = result.text_content or ""
    except Exception as e:
        logger.error("MarkItDown failed for %s: %s", file_path, e)
        text = ""

    if text.strip():
        return text

    # 2. MarkItDown returned nothing — try OCR (local only, easyocr may not be installed)
    try:
        import easyocr  # noqa: F401
    except ImportError:
        logger.warning("easyocr not installed — skipping OCR for %s", file_path)
        return text

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        logger.info("Scanned PDF detected, running OCR: %s", file_path)
        return _ocr_pdf(file_path)
    if ext in _IMAGE_EXTS:
        logger.info("Image file detected, running OCR: %s", file_path)
        return _ocr_image(file_path)

    return text
