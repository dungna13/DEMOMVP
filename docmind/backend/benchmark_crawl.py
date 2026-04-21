import asyncio
import time
import base64
import httpx
from services.crawler import crawl_and_collect_pdfs
from services.ingestor import ingest_pdf_smart
from services.legal_processor import process_legal_document

async def benchmark():
    print("=== DOCMIND PERFORMANCE BENCHMARK ===")
    target_url = "https://vanban.chinhphu.vn/he-thong-van-ban?classid=0&mode=1"
    max_docs = 3 # Thử nghiệm với 3 văn bản để tiết kiệm thời gian
    
    print(f"1. Đang quét danh sách văn bản từ: {target_url}...")
    docs = await crawl_and_collect_pdfs(target_url, max_documents=max_docs)
    
    if not docs:
        print("Không tìm thấy văn bản nào để test.")
        return

    results = []
    total_start_time = time.time()

    for i, doc in enumerate(docs):
        print(f"\n--- Đang xử lý văn bản {i+1}/{max_docs}: {doc.document_number} ---")
        start_time = time.time()
        
        try:
            # Bước 1: Tải file
            print(f"   [+] Đang tải PDF: {doc.pdf_url}")
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(doc.pdf_url)
                pdf_bytes = resp.content
            
            # Bước 2: Ingest (OCR)
            print(f"   [+] Đang chạy OCR (EasyOCR AI Local)...")
            b64_content = base64.b64encode(pdf_bytes).decode("utf-8")
            doc_info = {
                "document_number": doc.document_number,
                "issuance_date": doc.issue_date
            }
            text, was_ocr = await ingest_pdf_smart(b64_content, doc_info)
            
            # Đếm số trang (dựa trên marker [[PAGE_X]])
            page_count = text.count("[[PAGE_")
            
            # Bước 3: Phân tích AI (Gemini)
            print(f"   [+] Đang phân tích nội dung (Gemini AI)...")
            chunks = await process_legal_document(text)
            
            end_time = time.time()
            duration = end_time - start_time
            
            results.append({
                "number": doc.document_number,
                "pages": page_count,
                "was_ocr": was_ocr,
                "duration": duration
            })
            
            type_str = "SCAN (OCR)" if was_ocr else "TEXT (Direct)"
            print(f"   => HOÀN TẤT: {duration:.2f} giây | {page_count} trang | Loại: {type_str}")

        except Exception as e:
            print(f"   [!] Lỗi khi xử lý {doc.document_number}: {e}")

    # TỔNG KẾT
    print("\n" + "="*50)
    print("TỔNG KẾT HIỆU NĂNG")
    print("="*50)
    
    if not results:
        print("Không có kết quả thành công.")
        return

    total_duration = sum(r['duration'] for r in results)
    total_pages = sum(r['pages'] for r in results)
    avg_per_doc = total_duration / len(results)
    avg_per_page = total_duration / total_pages if total_pages > 0 else 0

    for r in results:
        type_str = "SCAN" if r['was_ocr'] else "TEXT"
        print(f"Văn bản {r['number']}: {r['duration']:.2f}s ({r['pages']} trang, {type_str})")
    
    print("-" * 20)
    print(f"THỜI GIAN TRUNG BÌNH / VĂN BẢN: {avg_per_doc:.2f} giây")
    print(f"THỜI GIAN TRUNG BÌNH / TRANG:    {avg_per_page:.2f} giây")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(benchmark())
