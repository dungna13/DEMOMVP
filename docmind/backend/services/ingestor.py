"""
Document Ingestor — Extracts text from PDF and text files.
Supports both text-based and scanned (image) PDFs via Tesseract OCR (FREE, LOCAL).
No API tokens required for OCR!
"""
import base64
import io
import os
import sys
import pymupdf
fitz = pymupdf  # Maintain compatibility

import pytesseract
from PIL import Image
from typing import Tuple, List


# ---------------------------------------------------------------------------
# Tesseract Configuration
# ---------------------------------------------------------------------------

# Auto-detect Tesseract path on Windows
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\Admin\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
]

for _path in _TESSERACT_PATHS:
    if os.path.exists(_path):
        pytesseract.pytesseract.tesseract_cmd = _path
        print(f"[Ingestor] Tesseract found at: {_path}")
        break
else:
    # On Linux/macOS, tesseract is usually in PATH
    if sys.platform != "win32":
        print("[Ingestor] Using system Tesseract from PATH")
    else:
        print("[Ingestor] WARNING: Tesseract not found! OCR will not work.")
        print("[Ingestor] Install from: https://github.com/UB-Mannheim/tesseract/wiki")


# ---------------------------------------------------------------------------
# PDF Scanning Detection
# ---------------------------------------------------------------------------

def is_scanned_pdf(doc) -> bool:
    """
    Detect if a PDF is a scanned document or a digitally-signed PDF
    where only the signature metadata is extractable as text.
    
    Vietnamese government PDFs (.signed.pdf) often have:
    - Digital signature overlay with signer info (short text)
    - Actual content rendered as images (not extractable as text)
    """
    signature_keywords = [
        "người ký", "email:", "cơ quan:", "thời gian ký",
        "chữ ký số", "signed", "signature", "certificate",
        "thongtinchinhphu", "chinhphu.vn", "văn phòng chính phủ",
        "cổng thông tin điện tử"
    ]
    
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
    
    # Check 2: Text is mostly digital signature metadata → treat as scanned
    sig_matches = sum(1 for kw in signature_keywords if kw in all_text)
    content_ratio = total_text_len / max(len(doc), 1)
    
    if sig_matches >= 3 and content_ratio < 500:
        print(f"[Ingestor] Detected digitally-signed PDF ({sig_matches} sig keywords, {content_ratio:.0f} chars/page)")
        return True
    
    return False


# ---------------------------------------------------------------------------
# Image Extraction
# ---------------------------------------------------------------------------

def extract_page_images(doc) -> List[bytes]:
    """Convert each PDF page to a PNG image for OCR."""
    images = []
    for page in doc:
        # Render at 2x resolution for better OCR accuracy
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        images.append(img_bytes)
    return images


# ---------------------------------------------------------------------------
# Tesseract OCR (FREE — No API needed!)
# ---------------------------------------------------------------------------

def ocr_with_tesseract(page_images: List[bytes]) -> str:
    """
    Use Tesseract OCR to extract text from scanned PDF pages.
    Completely FREE and LOCAL — no API tokens needed!
    
    Supports Vietnamese (vie) + English (eng) languages.
    """
    all_text = []
    
    for i, img_bytes in enumerate(page_images):
        page_num = i + 1
        print(f"[OCR-Tesseract] Processing page {page_num}/{len(page_images)}...")
        
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(img_bytes))
            
            # Run Tesseract with Vietnamese + English language
            # --oem 3 = Default LSTM engine
            # --psm 6 = Assume uniform block of text
            custom_config = r'--oem 3 --psm 6'
            
            # Try Vietnamese first, fallback to English
            try:
                text = pytesseract.image_to_string(
                    image, 
                    lang='vie+eng',
                    config=custom_config
                )
            except pytesseract.TesseractError:
                # Vietnamese language pack not installed, use English only
                print(f"[OCR-Tesseract] Vietnamese pack not found, using English only")
                text = pytesseract.image_to_string(
                    image, 
                    lang='eng',
                    config=custom_config
                )
            
            if text.strip():
                all_text.append(f"\n[[PAGE_{page_num}]]\n{text.strip()}")
            else:
                all_text.append(f"\n[[PAGE_{page_num}]]\n[Trang trống hoặc không đọc được]")
                
        except Exception as e:
            print(f"[OCR-Tesseract] Error on page {page_num}: {e}")
            all_text.append(f"\n[[PAGE_{page_num}]]\n[LỖI OCR: {str(e)}]")
    
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
    - If scanned/signed: use Tesseract OCR (free, local).

    Returns: (extracted_text, was_ocr_used)
    """
    pdf_data = base64.b64decode(b64_content)
    doc = fitz.open(stream=pdf_data, filetype="pdf")

    if is_scanned_pdf(doc):
        print(f"[Ingestor] Detected SCANNED/SIGNED PDF ({len(doc)} pages). Using Tesseract OCR (FREE)...")
        page_images = extract_page_images(doc)
        doc.close()
        # Tesseract is synchronous, run directly
        text = ocr_with_tesseract(page_images)
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