"""
Document Ingestor — Extracts text from PDF and text files.
Uses EasyOCR (Deep Learning AI - Local) for near-perfect accuracy.
No API tokens required!
"""
import base64
import io
import os
import pymupdf
fitz = pymupdf

import easyocr
import numpy as np
from PIL import Image
from typing import Tuple, List

# Initialize EasyOCR Reader (Local AI)
# This will download the model weights (~100MB) on the first run
_reader = None

def get_reader():
    global _reader
    if _reader is None:
        print("[Ingestor] Initializing EasyOCR (Vietnamese)...")
        # lang_list=['vi'] for Vietnamese
        _reader = easyocr.Reader(['vi', 'en'], gpu=False) # Set gpu=True if you have NVIDIA GPU
    return _reader


def is_scanned_pdf(doc) -> bool:
    """Detect scanned or signed PDFs."""
    pages_to_check = min(3, len(doc))
    total_text = ""
    for i in range(pages_to_check):
        total_text += doc[i].get_text().strip()
    
    # If text is very short or contains signature keywords with little else
    if len(total_text) < 200 or "người ký" in total_text.lower():
        return True
    return False


def extract_page_images(doc) -> List[bytes]:
    """Convert each PDF page to high-res image for AI OCR."""
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        images.append(img_bytes)
    return images


def clean_legal_text(text: str, doc_info: dict = None) -> str:
    """
    Advanced cleanup for Vietnamese legal documents.
    Uses metadata from the web to 'heal' OCR errors.
    """
    # 1. Manual replacements for common OCR artifacts
    replacements = {
        ".yn": ".vn",
        "chinhphu.yn": "chinhphu.vn",
        "Hội ẩồng": "Hội đồng",
        "Căn cứú": "Căn cứ",
        "co cấu": "cơ cấu",
        "Nguời": "Người",
        "quyét": "quyết",
        "định": "định",
        "ngàv": "ngày",
        "thảng": "tháng",
        "năm2": "năm 2",
        "IQĐ": "/QĐ",
        "IQT": "/QT",
        "~": "-",
        " . ": ". ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # 2. Remove noise from "Đến giờ/Ngày" stamps (Regex)
    import re
    # Remove lines like "Nedy:_ASLS 864 41.2626" or "ĐẾN Giv:..."
    text = re.sub(r'(?i)(ĐẾN Giờ|Nedy|Giv|ASLS|CỔNG THÔNG TIN).*?\d{2,4}', '', text)
    
    # 3. HEALING: Use 100% correct web metadata if available
    if doc_info:
        # Fix Document Number (e.g., if OCR read 692 instead of 689)
        official_number = doc_info.get("document_number")
        if official_number:
            # Try to find something that looks like the number and fix it
            # e.g., "682/QĐ-TTg" -> "689/QĐ-TTg"
            num_part = official_number.split('/')[0]
            text = re.sub(r'Số:\s*\w+/', f'Số:{num_part}/', text)
            text = text.replace(num_part.replace('9', '2'), num_part) # Fix 9/2 confusion
            text = text.replace(num_part.replace('8', 'B'), num_part) # Fix 8/B confusion

        # Fix Date (Only the main document date, usually following 'Hà Nội')
        official_date = doc_info.get("issuance_date") 
        if official_date and "/" in official_date:
            d, m, y = official_date.split("/")
            # Only match dates that follow "Hà Nội" or "ngày" at the very beginning of lines
            # This prevents overwriting dates of Laws/Decrees mentioned in the body
            header_date_pattern = r'(Hà Nội|ngày)\s*.*?\s*tháng\s*' + str(int(m)) + r'\s*năm\s*' + y
            correct_date = rf"\1, ngày {int(d)} tháng {int(m)} năm {y}"
            
            # Use count=1 to only replace the first occurrence (usually the header date)
            text = re.sub(header_date_pattern, correct_date, text, count=1, flags=re.IGNORECASE)

    # 4. Fix time format
    text = re.sub(r'(\d{2})\.(\d{2})\.(\d{2})', r'\1:\2:\3', text)
    
    # Remove empty lines and clean up whitespace
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 3]
    return "\n".join(lines)


def ocr_with_ai_local(page_images: List[bytes], doc_info: dict = None) -> str:
    """
    OCR with Metadata Healing.
    """
    reader = get_reader()
    all_text = []
    from PIL import ImageEnhance, ImageOps
    
    for i, img_bytes in enumerate(page_images):
        page_num = i + 1
        print(f"[AI-OCR] Healing Processing page {page_num}/{len(page_images)}...")
        
        try:
            image = Image.open(io.BytesIO(img_bytes)).convert('L')
            w, h = image.size
            image = image.resize((w*2, h*2), Image.Resampling.LANCZOS)
            image = ImageEnhance.Contrast(image).enhance(2.0)
            
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            
            results = reader.readtext(img_byte_arr.getvalue(), detail=0, paragraph=True)
            
            if results:
                page_text = "\n".join(results)
                # Apply the HEALING cleanup
                page_text = clean_legal_text(page_text, doc_info)
                all_text.append(f"\n[[PAGE_{page_num}]]\n{page_text}")
            else:
                all_text.append(f"\n[[PAGE_{page_num}]]\n[Trang trống]")
                
        except Exception as e:
            all_text.append(f"\n[[PAGE_{page_num}]]\n[LỖI OCR: {str(e)}]")
    
    return "\n\n".join(all_text)


async def ingest_pdf_smart(b64_content: str, doc_info: dict = None) -> Tuple[str, bool]:
    """Smart ingestion using Local AI OCR."""
    pdf_data = base64.b64decode(b64_content)
    doc = fitz.open(stream=pdf_data, filetype="pdf")

    if is_scanned_pdf(doc):
        print(f"[Ingestor] Using Local AI OCR (EasyOCR) with Healing...")
        page_images = extract_page_images(doc)
        doc.close()
        text = ocr_with_ai_local(page_images, doc_info)
        return text, True
    else:
        text = ""
        for i, page in enumerate(doc):
            text += f"\n[[PAGE_{i + 1}]]\n{page.get_text()}"
        doc.close()
        return text, False

def get_text_from_source(source_type: str, content: str) -> str:
    if source_type == "pdf":
        pdf_data = base64.b64decode(content)
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        text = "".join([p.get_text() for p in doc])
        doc.close()
        return text
    return content