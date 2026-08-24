from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import random
import logging

# Initialize FastAPI app
app = FastAPI(title="India Price Finder API")

# Enable CORS so the frontend can call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# User-Agent list to rotate and avoid instant blocking
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.google.com/"
    }

def scrape_amazon(query: str):
    logger.info(f"Scraping Amazon for: {query}")
    url = f"https://www.amazon.in/s?k={query}"
    results = []
    
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code != 200:
            logger.error(f"Amazon returned status {response.status_code}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        # Amazon results are typically in divs with data-component-type="s-search-result"
        items = soup.find_all("div", {"data-component-type": "s-search-result"}, limit=3)

        for item in items:
            try:
                title_el = item.find("h2")
                title = title_el.text.strip() if title_el else "No Title Found"
                
                price_el = item.find("span", class_="a-price-whole")
                price = price_el.text.strip() if price_el else "Price Unavailable"
                
                img_el = item.find("img", class_="s-image")
                img_url = img_el["src"] if img_el else ""
                
                # Clean price: remove commas and add currency
                clean_price = f"₹{price.replace(',', '')}" if price != "Price Unavailable" else price

                results.append({
                    "store": "Amazon.in",
                    "title": title,
                    "price": clean_price,
                    "image": img_url,
                    "link": "https://www.amazon.in" + item.find("a", class_="a-link-normal")["href"] if item.find("a", class_="a-link-normal") else "#"
                })
            except Exception as e:
                logger.warning(f"Error parsing Amazon item: {e}")
                continue
    except Exception as e:
        logger.error(f"Amazon request failed: {e}")
        
    return results

def scrape_flipkart(query: str):
    logger.info(f"Scraping Flipkart for: {query}")
    url = f"https://www.flipkart.com/search?q={query}"
    results = []
    
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code != 200:
            logger.error(f"Flipkart returned status {response.status_code}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        
        # Flipkart uses varying classes, so we look for common patterns in search result containers
        # These classes change often; in a real app, we'd use a more robust selector or a JSON-LD parser
        items = soup.find_all("div", {"class": lambda x: x and '_1AtVbE' in x}, limit=3) 
        
        # Fallback: try different common Flipkart container classes if the first one fails
        if not items:
            items = soup.select("div[class*='_75776f'], div[class*='_1AtVbE']", limit=3)

        for item in items:
            try:
                # Flipkart titles are often in a div with a specific class
                title_el = item.find("div", {"class": lambda x: x and '_4rR01T' in x}) or item.find("a", {"class": lambda x: x and '_2WkS7u' in x})
                title = title_el.text.strip() if title_el else "No Title Found"
                
                price_el = item.find("div", {"class": lambda x: x and '_30jeq3' in x})
                price = price_el.text.strip() if price_el else "Price Unavailable"
                
                img_el = item.find("img")
                img_url = img_el["src"] if img_el else ""
                
                clean_price = f"₹{price.replace(',', '').replace('₹', '')}" if price != "Price Unavailable" else price

                results.append({
                    "store": "Flipkart",
                    "title": title,
                    "price": clean_price,
                    "image": img_url,
                    "link": "https://www.flipkart.com" + item.find("a")["href"] if item.find("a") else "#"
                })
            except Exception as e:
                logger.warning(f"Error parsing Flipkart item: {e}")
                continue
    except Exception as e:
        logger.error(f"Flipkart request failed: {e}")
        
    return results

@app.get("/search")
async def search_products(q: str = Query(..., description="Product name to search for")):
    if not q:
        raise HTTPException(status_code=400, detail="Search query 'q' is required")
    
    # Execute scraping in parallel (simulated here by sequential calls for simplicity)
    amazon_results = scrape_amazon(q)
    flipkart_results = scrape_flipkart(q)
    
    combined_results = amazon_results + flipkart_results
    
    # Sort by price if possible (requires numeric conversion)
    def try_extract_price(p):
        try:
            return int(''.join(filter(str.isdigit, p)))
        except:
            return float('inf')

    sorted_results = sorted(combined_results, key=lambda x: try_extract_price(x['price']))

    return {
        "query": q,
        "total_found": len(sorted_results),
        "results": sorted_results
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
