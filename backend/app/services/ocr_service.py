import logging
from io import BytesIO

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 20
PDF_RENDER_DPI = 150
MAX_RENDERED_PAGE_PIXELS = 20_000_000
MAX_IMAGE_PIXELS = 20_000_000
_ocr_engine = None


def _get_ocr_engine():
    """Load PaddleOCR on first use so API imports and tests stay lightweight."""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # This is also the setting used by the existing PaddleOCR smoke
            # script and avoids slow/unstable oneDNN kernels on this CPU host.
            enable_mkldnn=False,
        )
    return _ocr_engine


def extract_text_from_image(image_bytes: bytes):
    """
    Extract invoice text using PaddleOCR 3.x.
    """

    if not image_bytes:
        raise ValueError("Uploaded image is empty")

    try:
        # Decode uploaded image bytes.
        with Image.open(BytesIO(image_bytes)) as decoded_image:
            if decoded_image.format not in {"PNG", "JPEG"}:
                raise ValueError("Only PNG and JPEG image content is supported")
            if decoded_image.width * decoded_image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions exceed the processing limit")
            image = decoded_image.convert("RGB")

        # Convert image into NumPy array.
        image_array = np.array(image)

        # Run PaddleOCR.
        results = _get_ocr_engine().predict(image_array)

        extracted_lines = []

        for result in results:
            result_data = result.json

            # PaddleOCR 3.x returns structured prediction results.
            if isinstance(result_data, dict):
                result_data = result_data.get("res", result_data)

            recognized_texts = result_data.get("rec_texts", [])

            for text in recognized_texts:
                if text and str(text).strip():
                    extracted_lines.append(str(text).strip())

        extracted_text = "\n".join(extracted_lines)

        if not extracted_text:
            raise ValueError("PaddleOCR could not recognize any text")

        return {
            "status": "success",
            "extracted_text": extracted_text
        }

    except Exception as e:
        logger.exception("PaddleOCR extraction failed")
        raise ValueError(f"OCR extraction failed: {str(e)}") from e


def extract_text_from_pdf(pdf_bytes: bytes) -> dict:
    """Render a bounded PDF page by page and reuse the image OCR pipeline."""
    if not pdf_bytes:
        raise ValueError("Uploaded PDF is empty")

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF processing requires PyMuPDF (pymupdf)") from exc

    page_texts = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported")
            if document.page_count < 1:
                raise ValueError("PDF contains no pages")
            if document.page_count > MAX_PDF_PAGES:
                raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit")

            scale = PDF_RENDER_DPI / 72
            matrix = fitz.Matrix(scale, scale)
            for page_number, page in enumerate(document, start=1):
                page_rect = page.rect
                if page_rect.width * scale * page_rect.height * scale > MAX_RENDERED_PAGE_PIXELS:
                    raise ValueError(
                        f"PDF page {page_number} dimensions exceed the processing limit"
                    )
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                if pixmap.width * pixmap.height > MAX_RENDERED_PAGE_PIXELS:
                    raise ValueError(
                        f"PDF page {page_number} dimensions exceed the processing limit"
                    )
                page_result = extract_text_from_image(pixmap.tobytes("png"))
                page_texts.append(f"--- Page {page_number} ---\n{page_result['extracted_text']}")

        return {"status": "success", "extracted_text": "\n\n".join(page_texts)}
    except ValueError:
        raise
    except Exception as e:
        logger.exception("PDF processing failed")
        raise ValueError(f"PDF is corrupted or could not be processed: {e}") from e
