
import httpx
import asyncio
from bs4 import BeautifulSoup

async def test_pagination():
    url = "https://vanban.chinhphu.vn/he-thong-van-ban?mode=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
        # Test maxresults
        test_url = f"{url}&maxresults=100"
        print(f"Testing {test_url}...")
        resp = await client.get(test_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.find_all("tr")
        print(f"Found {len(rows)} rows with maxresults=100")
        
        # Test page parameter
        test_url_p = f"{url}&p=2"
        print(f"Testing {test_url_p}...")
        resp_p = await client.get(test_url_p)
        if resp_p.text != resp.text:
            print("p=2 seems to work (content differs from page 1)")
        else:
            print("p=2 does NOT seem to work (same content as page 1)")

if __name__ == "__main__":
    asyncio.run(test_pagination())
