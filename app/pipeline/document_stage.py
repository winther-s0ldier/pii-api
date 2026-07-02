import os
import logging
import threading
import numpy as np
from markitdown import MarkItDown
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ponytail: lazy singleton — RapidOCR loads ONNX models once; ONNX InferenceSession is
# thread-safe so the same engine handles parallel page calls without a lock.
_ocr_engine = None
_ocr_lock = threading.Lock()


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        with _ocr_lock:
            if _ocr_engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _ocr_engine = RapidOCR()
                logger.info("RapidOCR engine loaded")
    return _ocr_engine


def _ocr_array(img: np.ndarray) -> str:
    result, _ = _get_ocr_engine()(img)
    if not result:
        return ""
    return "\n".join(item[1] for item in result)


def _ocr_pdf(file_path: str) -> str:
    try:
        import fitz
        doc = fitz.open(file_path)
        images = []
        for page in doc:
            # ponytail: text pages are fine at 150 DPI; image-only pages need 175 for accuracy
            dpi = 150 if page.get_text().strip() else 175
            pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            images.append(img)
        doc.close()

        if not images:
            return ""
        if len(images) == 1:
            return _ocr_array(images[0])

        # ponytail: parallel OCR safe because ONNX Runtime sessions are thread-safe;
        # ceiling: 4 workers — diminishing returns beyond 2 cores on t3.small
        with ThreadPoolExecutor(max_workers=min(len(images), 4)) as ex:
            results = list(ex.map(_ocr_array, images))
        return "\n\n".join(r for r in results if r)

    except Exception as e:
        logger.error("RapidOCR PDF failed: %s", e)
        return ""


def _ocr_image(file_path: str) -> str:
    try:
        result, _ = _get_ocr_engine()(file_path)
        if not result:
            return ""
        return "\n".join(item[1] for item in result)
    except Exception as e:
        logger.error("RapidOCR image failed: %s", e)
        return ""


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def extract_text(file_path: str) -> str:
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        return ""

    try:
        text = MarkItDown().convert(file_path).text_content or ""
    except Exception as e:
        logger.error("MarkItDown failed for %s: %s", file_path, e)
        text = ""

    if text.strip():
        return text

    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401
    except ImportError:
        logger.warning("rapidocr_onnxruntime not installed — skipping OCR for %s", file_path)
        return text

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        logger.info("Scanned PDF detected, running OCR: %s", file_path)
        return _ocr_pdf(file_path)
    if ext in _IMAGE_EXTS:
        logger.info("Image file detected, running OCR: %s", file_path)
        return _ocr_image(file_path)

    return text
