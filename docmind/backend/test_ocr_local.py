import asyncio
import base64
import os
from services.ingestor import ingest_pdf_smart

async def test_ocr():
    print("--- DOCMIND ULTRA-ACCURACY TEST (WITH HEALING) ---")
    
    test_pdf_url = "https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/4/689-ttg.signed.pdf"
    
    # GIẢ LẬP DỮ LIỆU CRAWLER (Đúng 100% từ Web)
    doc_info = {
        "document_number": "689/QĐ-TTg",
        "issuance_date": "14/04/2026"
    }
    
    import httpx
    print(f"1. Đang tải file test: {test_pdf_url}...")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(test_pdf_url)
        pdf_bytes = resp.content

    print("2. Đang chạy AI-OCR với cơ chế HEALING (Chữa lỗi bằng Metadata)...")
    b64_content = base64.b64encode(pdf_bytes).decode("utf-8")
    
    # TRUYỀN THÊM doc_info ĐỂ SỬA LỖI
    text, was_ocr = await ingest_pdf_smart(b64_content, doc_info)
    
    print("-" * 30)
    print(f"KẾT QUẢ SAU KHI ĐÃ 'HEAL':")
    print(text[:1200] + "...") 
    print("-" * 30)
    
    if "ngày 14 tháng 4 năm 2026" in text:
        print("✅ THÀNH CÔNG: Đã sửa lỗi 'J#' thành '14' chuẩn xác!")
    else:
        print("❌ CẢNH BÁO: Vẫn chưa sửa được lỗi ngày tháng.")

if __name__ == "__main__":
    asyncio.run(test_ocr())
