
import os
import asyncio
import base64
import httpx
from services import ingestor
from dotenv import load_dotenv

load_dotenv()

async def debug_file():
    url = "https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/4/691-ttg.signed.pdf"
    print(f"--- Downloading file from URL: {url} ---")
    
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(timeout=60.0, headers=headers, follow_redirects=True) as client:
        response = await client.get(url)
        if response.status_code != 200:
            print(f"Download failed: {response.status_code}")
            return
            
        b64_content = base64.b64encode(response.content).decode('utf-8')
        
        print("--- Running Smart Ingest (AI OCR) ---")
        # FORCE TEST
        text, was_ocr = await ingestor.ingest_pdf_smart(b64_content)
        
        print(f"\nTECHNICAL RESULTS:")
        print(f"- OCR Used: {was_ocr}")
        print(f"- Text Length: {len(text)} chars")
        print(f"- Word Count: {len(text.split())}")
        print("\n--- FIRST 500 CHARS ---")
        # Filter out potential non-utf8 for terminal safety
        safe_text = text[:500].encode('ascii', 'ignore').decode('ascii')
        print(safe_text)
        print("\n--- END ---")

if __name__ == "__main__":
    asyncio.run(debug_file())
