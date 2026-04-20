"""
Legal Document Processor for Vietnamese Government Documents.
Uses Gemini AI to clean OCR text, restore legal structure, 
and produce semantically meaningful chunks with metadata.
"""
import json
import os
import google.generativeai as genai
from typing import List, Dict, Optional, Tuple

LEGAL_PROCESSING_PROMPT = """
Bạn là một hệ thống AI chuyên xử lý văn bản pháp luật tiếng Việt để phục vụ hệ thống RAG (Retrieval-Augmented Generation).

Dữ liệu đầu vào là văn bản được trích xuất từ OCR của file PDF scan, có thể chứa:
- lỗi chính tả do OCR (ví dụ: "Diéu" thay vì "Điều")
- ký tự rác, ký tự thừa
- xuống dòng sai
- mất cấu trúc văn bản

NHIỆM VỤ CỦA BẠN:

Bước 1 — Làm sạch văn bản:
- Xóa ký tự rác, ký tự không cần thiết
- Sửa lỗi OCR phổ biến nếu có thể (nhưng không đoán nếu không chắc)
- Ghép các dòng bị ngắt sai thành câu hoàn chỉnh
- Giữ nguyên nội dung gốc, không thêm hoặc suy diễn

Bước 2 — Khôi phục cấu trúc pháp lý:
- Nhận diện và chuẩn hóa các thành phần:
  - Chương (nếu có)
  - Điều
  - Khoản
  - Điểm
- Đảm bảo format rõ ràng, dễ đọc

Bước 3 — Chunking theo ngữ nghĩa:
- Chia văn bản thành các đoạn (chunk) có ý nghĩa
- Mỗi chunk nên là:
  - 1 Điều, hoặc
  - 1 Khoản (nếu Điều quá dài)
- KHÔNG được cắt giữa chừng nội dung

Bước 4 — Gán metadata:
Với mỗi chunk, trích xuất:
- "dieu": số điều (nếu có)
- "khoan": số khoản (nếu có)
- "chuong": số chương (nếu có)
- "raw_text": nội dung chunk đã clean

YÊU CẦU OUTPUT:

Trả về JSON hợp lệ, dạng list:

[
  {
    "content": "Nội dung đã làm sạch và chuẩn hóa",
    "metadata": {
      "chuong": "I",
      "dieu": 1,
      "khoan": 2
    }
  }
]

QUY TẮC QUAN TRỌNG:
- Không được thêm thông tin ngoài văn bản gốc
- Không giải thích
- Không markdown
- Output phải parse được bằng JSON
- Nếu không xác định được metadata thì để null

DỮ LIỆU ĐẦU VÀO:
\"\"\"
{ocr_text}
\"\"\"
"""



DOC_INFO_PROMPT = """
Bạn là một chuyên gia phân tích văn bản pháp luật Việt Nam. 
NHIỆM VỤ: Hãy trích xuất thông tin định danh của văn bản từ đoạn nội dung sau.

DỮ LIỆU ĐẦU VÀO (thường là phần đầu văn bản):
\"\"\"
{header_text}
\"\"\"

YÊU CẦU OUTPUT:
Chỉ trả về JSON với định dạng sau, không giải thích thêm:
{
  "document_number": "Số hiệu văn bản (ví dụ: 691/QĐ-TTg)",
  "issuance_date": "Ngày ban hành (ví dụ: 15/04/2026)",
  "issuing_authority": "Cơ quan ban hành (ví dụ: Thủ tướng Chính phủ)"
}
Nếu không tìm thấy thông tin nào, hãy để giá trị là null.
"""


def get_model():
    """Get or create the Gemini model for legal processing."""
    return genai.GenerativeModel('gemini-1.5-flash')


async def extract_document_info(text: str) -> Dict[str, Optional[str]]:
    """
    Extract document number, date, and authority from the first part of the text.
    """
    # Only use the first 3000 characters for header info
    header = text[:3000]
    
    model = get_model()
    prompt = DOC_INFO_PROMPT.replace("{header_text}", header)
    
    try:
        response = await model.generate_content_async(prompt)
        result_text = response.text.strip()
        
        # Clean markdown
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
            
        info = json.loads(result_text)
        return {
            "document_number": info.get("document_number"),
            "issuance_date": info.get("issuance_date"),
            "issuing_authority": info.get("issuing_authority")
        }
    except Exception as e:
        print(f"[LegalProcessor] Meta extraction error: {e}")
        return {"document_number": None, "issuance_date": None, "issuing_authority": None}


async def process_legal_document(raw_text: str) -> List[Dict]:
    """
    Process raw OCR text from a Vietnamese legal document.
    Returns a list of structured chunks with metadata.
    """
    if not raw_text or len(raw_text.strip()) < 50:
        # Text too short, return as-is
        return [{
            "content": raw_text.strip(),
            "metadata": {"chuong": None, "dieu": None, "khoan": None}
        }]

    model = get_model()
    prompt = LEGAL_PROCESSING_PROMPT.replace("{ocr_text}", raw_text)

    try:
        response = await model.generate_content_async(prompt)
        result_text = response.text.strip()

        # Clean up potential markdown wrapping
        if result_text.startswith("```json"):
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif result_text.startswith("```"):
            result_text = result_text.split("```")[1].split("```")[0].strip()

        chunks = json.loads(result_text)

        # Validate structure
        validated = []
        for chunk in chunks:
            if isinstance(chunk, dict) and "content" in chunk:
                validated.append({
                    "content": chunk.get("content", ""),
                    "metadata": {
                        "chuong": chunk.get("metadata", {}).get("chuong"),
                        "dieu": chunk.get("metadata", {}).get("dieu"),
                        "khoan": chunk.get("metadata", {}).get("khoan"),
                    }
                })
        
        if validated:
            return validated

    except json.JSONDecodeError as e:
        print(f"[LegalProcessor] JSON parse error: {e}")
    except Exception as e:
        print(f"[LegalProcessor] Error: {e}")

    # Fallback: return raw text as single chunk
    return [{
        "content": raw_text.strip(),
        "metadata": {"chuong": None, "dieu": None, "khoan": None}
    }]


async def process_large_document(raw_text: str, max_chars_per_batch: int = 8000) -> List[Dict]:
    """
    Process a large document by splitting it into batches,
    sending each batch to the AI, then merging results.
    This avoids exceeding Gemini's context window.
    """
    if len(raw_text) <= max_chars_per_batch:
        return await process_legal_document(raw_text)

    # Split by paragraphs to avoid cutting mid-sentence
    paragraphs = raw_text.split("\n\n")
    batches = []
    current_batch = ""

    for para in paragraphs:
        if len(current_batch) + len(para) > max_chars_per_batch and current_batch:
            batches.append(current_batch)
            current_batch = para
        else:
            current_batch += "\n\n" + para if current_batch else para

    if current_batch:
        batches.append(current_batch)

    print(f"[LegalProcessor] Document split into {len(batches)} batches")

    all_chunks = []
    for i, batch in enumerate(batches):
        print(f"[LegalProcessor] Processing batch {i+1}/{len(batches)}...")
        batch_chunks = await process_legal_document(batch)
        all_chunks.extend(batch_chunks)

    return all_chunks
