"""
Document Ingestor — Extracts text from PDF and text files.
Supports both text-based and scanned (image) PDFs via Gemini Vision OCR.
"""
import base64
import io
import os
import asyncio
import random
import pymupdf
fitz = pymupdf  # Maintain compatibility

import google.generativeai as genai
from typing import Tuple, List


# ---------------------------------------------------------------------------
# Scanned PDF detection
# ---------------------------------------------------------------------------

_SIGNATURE_KEYWORDS = [
    "người ký", "email:", "cơ quan:", "thời gian ký",
    "chữ ký số", "signed", "signature", "certificate",
    "thongtinchinhphu", "chinhphu.vn", "văn phòng chính phủ",
    "cổng thông tin điện tử",
]


def is_scanned_pdf(doc) -> bool:
    """
    Detect if a PDF is a scanned document or a digitally-signed PDF
    where only the signature metadata is extractable as text.

    Vietnamese government PDFs (.signed.pdf) often have:
    - Digital signature overlay with signer info (short text)
    - Actual content rendered as images (not extractable as text)
    """
    pages_to_check = min(5, len(doc))
    total_text_len = 0
    all_text = ""

    for i in range(pages_to_check):
        page_text = doc[i].get_text().strip()
        total_text_len += len(page_text)
        all_text += page_text.lower() + " "

    avg_text = total_text_len / pages_to_check if pages_to_check > 0 else 0

    # Check 1: Very little text overall → scanned
    if avg_text < 100:
        return True

    # Check 2: Text exists but is mostly digital signature metadata → treat as scanned
    sig_matches = sum(1 for kw in _SIGNATURE_KEYWORDS if kw in all_text)
    content_ratio = total_text_len / max(len(doc), 1)

    if sig_matches >= 3 and content_ratio < 500:
        print(
            f"[Ingestor] Detected digitally-signed PDF with signature-only text "
            f"({sig_matches} sig keywords, {content_ratio:.0f} chars/page)"
        )
        return True

    return False


# ---------------------------------------------------------------------------
# Page image extraction
# ---------------------------------------------------------------------------

def extract_page_images(doc) -> List[bytes]:
    """Convert each PDF page to a PNG image for OCR."""
    images = []
    for page in doc:
        # Render at 2x resolution for better OCR accuracy
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        images.append(img_bytes)
    return images


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

async def ocr_with_gemini(page_images: List[bytes]) -> str:
    """
    Use Gemini Vision to OCR scanned PDF pages.
    Added retry logic and delays to handle rate limits.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)

    model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
    all_text = []

    # Process pages in smaller batches for stability
    batch_size = 3

    for i in range(0, len(page_images), batch_size):
        batch = page_images[i:i + batch_size]
        page_range = f"{i+1}-{min(i+batch_size, len(page_images))}"

        max_retries = 3
        curr_retry = 0
        success = False

        while curr_retry < max_retries and not success:
            try:
                print(f"[OCR] Processing pages {page_range} (Attempt {curr_retry + 1})...")

                parts = [
                    "Bạn là một hệ thống OCR chuyên dụng cho văn bản pháp luật tiếng Việt.\n"
                    "Hãy trích xuất chính xác 100% nội dung văn bản từ các hình ảnh sau.\n"
                    "Không bỏ sót bất kỳ Điều, Khoản hay con số nào.\n\n"
                ]

                for j, img_bytes in enumerate(batch):
                    parts.append({"mime_type": "image/png", "data": img_bytes})
                    parts.append(f"\n[[PAGE_{i + j + 1}]]\n")

                response = await model.generate_content_async(parts)
                if response.text:
                    all_text.append(response.text)
                    success = True
                    await asyncio.sleep(1.5)

            except Exception as e:
                curr_retry += 1
                wait_time = (2 ** curr_retry) + random.random()
                print(f"[OCR] Error on pages {page_range}: {e}. Retrying in {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)

        if not success:
            print(f"[OCR] CRITICAL: Failed to process pages {page_range} after {max_retries} attempts.")
            all_text.append(f"\n[LỖI OCR: Không thể đọc các trang {page_range} do sự cố kết nối máy chủ AI]\n")

    return "\n\n".join(all_text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_pdf(b64_content: str) -> str:
    """Extract text from a text-based PDF."""
    pdf_data = base64.b64decode(b64_content)
    doc = fitz.open(stream=pdf_data, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


async def ingest_pdf_smart(b64_content: str) -> Tuple[str, bool]:
    """
    Smart PDF ingestion:
    - If text-based: extract text directly (fast).
    - If scanned/signed: use Gemini Vision OCR (slower but accurate).

    Returns: (extracted_text, was_ocr_used)

    NOTE: For signed Vietnamese government PDFs, PyMuPDF only extracts the
    digital signature overlay (signer name, email, timestamp). The actual
    document content is embedded as an image → must use OCR.
    To avoid calling this twice (once for doc_info, once for chunking),
    callers in sources.py should cache the result and pass it in.
    """
    pdf_data = base64.b64decode(b64_content)
    doc = fitz.open(stream=pdf_data, filetype="pdf")

    if is_scanned_pdf(doc):
        print(f"[Ingestor] Detected SCANNED/SIGNED PDF ({len(doc)} pages). Using AI OCR...")
        page_images = extract_page_images(doc)
        doc.close()
        text = await ocr_with_gemini(page_images)
        return text, True
    else:
        print(f"[Ingestor] Detected TEXT-BASED PDF ({len(doc)} pages). Direct extraction.")
        text = ""
        for i, page in enumerate(doc):
            text += f"\n[[PAGE_{i + 1}]]\n"
            text += page.get_text()
        doc.close()
        return text, False


def ingest_text(content: str) -> str:
    """Extract text from a text or base64-encoded text file."""
    try:
        if ';' in content and 'base64,' in content:
            content = content.split('base64,')[1]
        decoded = base64.b64decode(content).decode('utf-8')
        return decoded
    except Exception:
        return content


def get_text_from_source(source_type: str, content: str) -> str:
    """Synchronous text extraction (backward compatible)."""
    if source_type == "pdf":
        return ingest_pdf(content)
    elif source_type == "text":
        return ingest_text(content)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")