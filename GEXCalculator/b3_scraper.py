"""
B3 Options Scraper Module
Extracts options data from B3's open positions page using Selenium for JS-rendered content.
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import json
import time
from typing import Optional


def convert_br_number(value: str) -> float:
    """
    Convert Brazilian number format to float.
    Example: '262.701' -> 262701, '116,00' -> 116.0
    """
    if not value or value.strip() == '':
        return 0.0
    # Remove thousands separator (.)
    value = value.replace('.', '')
    # Replace decimal separator (,) with (.)
    value = value.replace(',', '.')
    try:
        return float(value)
    except ValueError:
        return 0.0


def infer_option_type(ticker: str) -> str:
    """
    Infer option type from ticker.
    Letters A-L (months 1-12) are Calls
    Letters M-X (months 1-12) are Puts
    The 5th character is the month indicator.
    """
    if len(ticker) < 5:
        return 'UNKNOWN'
    month_char = ticker[4].upper()
    if 'A' <= month_char <= 'L':
        return 'CALL'
    elif 'M' <= month_char <= 'X':
        return 'PUT'
    return 'UNKNOWN'


def get_chrome_driver() -> webdriver.Chrome:
    """Create and configure Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def fetch_options_with_selenium(date: str, empresa_emissora: str = "ISHARES IBOVESPA FUNDO DE ÍNDICE") -> list:
    """
    Fetch options data using Selenium to handle JavaScript-rendered content.
    Handles pagination to get ALL options.
    
    Args:
        date: Date in DD/MM/YYYY format
        empresa_emissora: Company name for options
    
    Returns:
        List of dictionaries with options data
    """
    import urllib.parse
    
    base_url = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-a-vista/opcoes/posicoes-em-aberto/posicoes-em-aberto-8AA8D0CC95C8AC560196115CDC242213.htm"
    
    params = {
        'empresaEmissora': empresa_emissora,
        'data': date,
        'f': '0'
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    print(f"Opening browser to fetch data from B3...")
    driver = get_chrome_driver()
    
    try:
        driver.get(url)
        
        # Wait for tables to load
        print("Waiting for page to load...")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.responsive"))
        )
        
        # Scroll to bottom to trigger lazy loading of all content
        last_height = driver.execute_script("return document.body.scrollHeight")
        max_scroll_attempts = 10
        for i in range(max_scroll_attempts):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # Scroll back to top and wait a bit more
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        # Execute JavaScript to extract all data from ALL tables
        extraction_script = """
        return (() => {
            const result = [];
            const tables = document.querySelectorAll('table.responsive');
            
            console.log('Found ' + tables.length + ' tables');
            
            tables.forEach((table, tableIdx) => {
                let headerText = '';
                
                // Look for the closest heading or paragraph before the table
                let sibling = table.previousElementSibling;
                let searchCount = 0;
                while (sibling && !headerText && searchCount < 10) {
                    if (sibling.innerText && (sibling.innerText.includes('Vencimento') || sibling.innerText.includes('Opções de'))) {
                        headerText = sibling.innerText;
                    }
                    sibling = sibling.previousElementSibling;
                    searchCount++;
                }
                
                // If not found, look at the parent's previous sibling
                if (!headerText) {
                    let parentSibling = table.parentElement.previousElementSibling;
                    searchCount = 0;
                    while (parentSibling && !headerText && searchCount < 10) {
                        if (parentSibling.innerText && (parentSibling.innerText.includes('Vencimento') || parentSibling.innerText.includes('Opções de'))) {
                            headerText = parentSibling.innerText;
                        }
                        parentSibling = parentSibling.previousElementSibling;
                        searchCount++;
                    }
                }
                
                // Try looking in parent container
                if (!headerText) {
                    const parent = table.closest('.card, .section, .container, div');
                    if (parent) {
                        const headers = parent.querySelectorAll('h1, h2, h3, h4, h5, p');
                        for (let h of headers) {
                            if (h.innerText && (h.innerText.includes('Vencimento') || h.innerText.includes('Opções de'))) {
                                headerText = h.innerText;
                                break;
                            }
                        }
                    }
                }
                
                const isPut = headerText.toLowerCase().includes('venda');
                const optionType = isPut ? 'PUT' : 'CALL';
                const expiryMatch = headerText.match(/(\\d{2}\\/\\d{2}\\/\\d{4})/);
                const expiry = expiryMatch ? expiryMatch[1] : null;
                
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 6) {
                        const ticker = cells[0].innerText.trim();
                        // Skip if ticker is empty or looks like a header
                        if (ticker && ticker.length > 3 && !ticker.includes('Código')) {
                            result.push({
                                ticker: ticker,
                                type: optionType,
                                strike: cells[1].innerText.trim(),
                                expiry: expiry,
                                open_interest: cells[5].innerText.trim()
                            });
                        }
                    }
                });
            });
            
            return result;
        })();
        """
        
        data = driver.execute_script(extraction_script)
        print(f"Extracted {len(data)} options from page")
        return data
        
    except Exception as e:
        print(f"Error during Selenium extraction: {e}")
        return []
    finally:
        driver.quit()


def parse_options_data(raw_data: list) -> pd.DataFrame:
    """
    Parse raw options data from JavaScript extraction.
    
    Args:
        raw_data: List of dictionaries from JS extraction
    
    Returns:
        DataFrame with cleaned data
    """
    if not raw_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(raw_data)
    
    # Convert strike to float
    df['strike'] = df['strike'].apply(convert_br_number)
    
    # Convert open interest to int
    df['open_interest'] = df['open_interest'].apply(lambda x: int(convert_br_number(x)))
    
    # Convert expiry to datetime
    df['expiry'] = pd.to_datetime(df['expiry'], format='%d/%m/%Y', errors='coerce')
    
    # Use inferred type if type is CALL but ticker suggests PUT (or vice versa)
    # This is a fallback validation
    def validate_type(row):
        inferred = infer_option_type(row['ticker'])
        if inferred != 'UNKNOWN':
            return inferred
        return row['type']
    
    df['type'] = df.apply(validate_type, axis=1)
    
    return df


def get_options_data(date: str) -> pd.DataFrame:
    """
    Main function to get BOVA11 options data from B3.
    
    Args:
        date: Reference date in DD/MM/YYYY format
    
    Returns:
        DataFrame with options data
    """
    print(f"Fetching B3 options data for {date}...")
    raw_data = fetch_options_with_selenium(date)
    df = parse_options_data(raw_data)
    print(f"Found {len(df)} options")
    return df


if __name__ == "__main__":
    # Test the scraper
    df = get_options_data("16/01/2026")
    print("\nFirst 20 options:")
    print(df.head(20))
    print(f"\nTotal options: {len(df)}")
    print(f"Calls: {len(df[df['type'] == 'CALL'])}")
    print(f"Puts: {len(df[df['type'] == 'PUT'])}")
    print(f"\nUnique expiries: {df['expiry'].unique()}")
