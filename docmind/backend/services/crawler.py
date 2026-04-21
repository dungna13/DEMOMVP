"""
Government Document Crawler for vanban.chinhphu.vn.
Automatically scrapes document listings, extracts PDF links,
and feeds them into the DocMind ingestion pipeline.
"""
import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class CrawledDocument:
    """A single document found on the government portal."""
    document_number: str       # Số ký hiệu (e.g., 689/QĐ-TTg)
    title: str                 # Trích yếu
    issue_date: str            # Ngày ban hành
    pdf_url: Optional[str]     # Direct link to PDF


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


async def crawl_chinhphu_page(
    url: str,
    max_results: int = 50,
    page: int = 1,
) -> List[CrawledDocument]:
    """
    Crawl a listing page from vanban.chinhphu.vn.
    """
    # Build URL with pagination
    separator = "&" if "?" in url else "?"
    if "p=" not in url:
        url = f"{url}{separator}p={page}"
    if "maxresults=" not in url:
        url = f"{url}&maxresults={max_results}"
    
    print(f"[Crawler] Fetching: {url}")
    
    async with httpx.AsyncClient(
        timeout=30.0, headers=BROWSER_HEADERS, follow_redirects=True
    ) as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                print(f"[Crawler] HTTP {response.status_code}")
                return []
        except Exception as e:
            print(f"[Crawler] Error fetching {url}: {e}")
            return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    documents: List[CrawledDocument] = []
    
    # Find all table rows that contain document data
    rows = soup.find_all("tr")
    
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        
        # Cell 0: Document number (inside <a><span>)
        doc_number = ""
        number_elem = cells[0].find("a")
        if number_elem:
            span = number_elem.find("span")
            doc_number = (span.get_text(strip=True) if span 
                         else number_elem.get_text(strip=True))
        else:
            doc_number = cells[0].get_text(strip=True)
        
        # Skip header rows
        if not doc_number or doc_number in ("Số ký hiệu", "STT"):
            continue
        
        # Cell 1: Issue date
        issue_date = cells[1].get_text(strip=True)
        
        # Cell 2: Title + PDF link
        title = ""
        pdf_url = None
        
        links_in_cell = cells[2].find_all("a")
        for link in links_in_cell:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            
            # Check if this is the PDF attachment link
            if "datafiles.chinhphu.vn" in href and href.endswith(".pdf"):
                if not href.startswith("http"):
                    href = "https:" + href if href.startswith("//") else href
                pdf_url = href
            elif text and "đính kèm" not in text.lower():
                # This is the title link
                title = text
        
        # If no title found from links, get full cell text
        if not title:
            title = cells[2].get_text(strip=True)[:200]
        
        documents.append(CrawledDocument(
            document_number=doc_number,
            title=title,
            issue_date=issue_date,
            pdf_url=pdf_url,
        ))
    
    print(f"[Crawler] Found {len(documents)} documents ({sum(1 for d in documents if d.pdf_url)} with PDF)")
    return documents


async def crawl_and_collect_pdfs(
    url: str,
    max_results: int = 50,
    max_documents: int = 10,
) -> List[CrawledDocument]:
    """
    Crawl documents and return only those with PDF links.
    Limits to max_documents to avoid overloading the system.
    """
    documents = await crawl_chinhphu_page(url, max_results)
    
    # Filter to only documents with PDF links and limit
    with_pdf = [d for d in documents if d.pdf_url][:max_documents]
    
    print(f"[Crawler] Returning {len(with_pdf)} documents with PDF links")
    return with_pdf
