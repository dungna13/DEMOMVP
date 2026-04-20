"""
Legal Document Processor for Vietnamese Government Documents.
Uses Gemini AI to clean OCR text, restore legal structure, 
and produce semantically meaningful chunks with metadata.
"""
import json
import os
import re
import google.generativeai as genai
from typing import List, Dict, Optional, Tuple

def clean_ai_json(text: str) -> str:
    """Extract only the JSON part from AI response, removing conversational filler."""
    # Find the first '[' or '{' and the last ']' or '}'
    text = text.strip()
    
    # Remove markdown code blocks if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    
    # Try to find the JSON array or object using regex if still messy
    match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
    if match:
        return match.group(1)
    
    return text

LEGAL_PROCESSING_PROMPT = """
Sử dụng dữ liệu OCR sau đây để trích xuất văn bản pháp luật.
LƯU Ý: Trong văn bản có các thẻ đánh dấu trang như [[PAGE_1]], [[PAGE_2]]... Hãy chú ý để biết nội dung thuộc trang nào.

NHIỆM VỤ:
1. Làm sạch văn bản (sửa lỗi chính tả OCR).
2. LOẠI BỎ hoàn toàn Header/Footer, Số hiệu, Ngày ban hành, Chữ ký.
3. Chia văn bản thành danh sách (JSON List) các Điều/Khoản.

YÊU CẦU OUTPUT:
Chỉ trả về JSON List theo định dạng này, không nói thêm:
[
  {
    "content": "Nội dung Điều 1...",
    "metadata": {
        "chuong": null, 
        "dieu": 1, 
        "khoan": null,
        "page": 1
    }
  }
]

DỮ LIỆU ĐẦU VÀO:
\"\"\"
{ocr_text}
\"\"\"
"""

DOC_INFO_PROMPT = """
Trích xuất thông tin định danh văn bản pháp luật Việt Nam.

DỮ LIỆU:
\"\"\"
{header_text}
\"\"\"

YÊU CẦU OUTPUT (Chỉ trả về JSON, không giải thích):
{
  "document_number": "Số hiệu",
  "issuance_date": "Ngày ban hành",
  "issuing_authority": "Cơ quan ban hành"
}
"""

def get_model():
    return genai.GenerativeModel('gemini-3.1-flash-lite-preview')

async def extract_document_info(text: str) -> Dict[str, Optional[str]]:
    header = text[:3000]
    model = get_model()
    try:
        response = await model.generate_content_async(DOC_INFO_PROMPT.replace("{header_text}", header))
        clean_json = clean_ai_json(response.text)
        info = json.loads(clean_json)
        return {
            "document_number": info.get("document_number"),
            "issuance_date": info.get("issuance_date"),
            "issuing_authority": info.get("issuing_authority")
        }
    except Exception as e:
        print(f"[LegalProcessor] Meta error: {e}")
        return {"document_number": None, "issuance_date": None, "issuing_authority": None}

async def process_legal_document(raw_text: str) -> List[Dict]:
    if not raw_text or len(raw_text.strip()) < 50:
        return [{"content": raw_text.strip(), "metadata": {"chuong": None, "dieu": None, "khoan": None}}]

    model = get_model()
    try:
        response = await model.generate_content_async(LEGAL_PROCESSING_PROMPT.replace("{ocr_text}", raw_text))
        clean_json = clean_ai_json(response.text)
        chunks = json.loads(clean_json)
        
        validated = []
        for chunk in chunks:
            if isinstance(chunk, dict) and "content" in chunk:
                validated.append({
                    "content": chunk.get("content", ""),
                    "metadata": {
                        "chuong": chunk.get("metadata", {}).get("chuong"),
                        "dieu": chunk.get("metadata", {}).get("dieu"),
                        "khoan": chunk.get("metadata", {}).get("khoan"),
                        "page": chunk.get("metadata", {}).get("page"),
                    }
                })
        return validated if validated else []
    except Exception as e:
        print(f"[LegalProcessor] Processing error: {e}")
        return []

async def process_large_document(raw_text: str, max_chars_per_batch: int = 8000) -> List[Dict]:
    if len(raw_text) <= max_chars_per_batch:
        return await process_legal_document(raw_text)

    paragraphs = raw_text.split("\n\n")
    batches = []
    current_batch = ""
    for para in paragraphs:
        if len(current_batch) + len(para) > max_chars_per_batch and current_batch:
            batches.append(current_batch)
            current_batch = para
        else:
            current_batch += "\n\n" + para if current_batch else para
    if current_batch: batches.append(current_batch)

    all_chunks = []
    for batch in batches:
        batch_chunks = await process_legal_document(batch)
        all_chunks.extend(batch_chunks)
    return all_chunks