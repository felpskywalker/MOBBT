"""
Opcoes.net.br Scraper Module
Extracts comprehensive options data (Ticker, Strike, Expiry, IV, Open Interest) from a single page.
Avoids multiple requests and B3 pagination issues.
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
from datetime import datetime
import re

def get_chrome_driver() -> webdriver.Chrome:
    """Create and configure Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Use headless mode for production
    chrome_options.add_argument("--window-size=1920,1080")
    # chrome_options.add_argument("--start-maximized") # Maximize to ensure elements are visible
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def fetch_opcoes_net_data(ticker="BOVA11"):
    """
    Fetch all options data from opcoes.net.br for a given underlying ticker.
    Returns DataFrame with columns: ticker, type, strike, expiry, iv, open_interest, market_price
    """
    url = f"https://opcoes.net.br/opcoes/bovespa/{ticker}"
    driver = get_chrome_driver()
    
    try:
        print(f"Accessing {url}...")
        driver.get(url)
        
        # Wait for page to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "grade-vencimentos-dates"))
        )
        time.sleep(3) # Extra wait for initial scripts
        
        # 1. Select ALL maturities (Vencimentos)
        print("Selecting all maturities...")
        checkboxes = driver.find_elements(By.CSS_SELECTOR, "#grade-vencimentos-dates input[type='checkbox']")
        for ck in checkboxes:
            if not ck.is_selected():
                try:
                    driver.execute_script("arguments[0].click();", ck)
                    time.sleep(0.1)
                except:
                    pass
        
        # Wait for table reload
        time.sleep(2)
        
        # 2. Select ALL strikes (Expand Range)
        print("Expanding strike range to maximum...")
        try:
            # Opcoes.net.br uses jQuery UI Slider. We can manipulate it via JS.
            # We set values to [0, 10000] to cover everything.
            driver.execute_script("""
                try {
                    var slider = $("#strike-range");
                    var min = slider.slider("option", "min");
                    var max = slider.slider("option", "max");
                    slider.slider("values", [min, max]);
                    // Trigger change/slide event to update table
                    slider.slider("option", "change").call(slider);
                    // Also try custom trigger
                    gradeOpcoes.CarregarGrade();
                } catch(e) {
                    console.log("Error updating slider: " + e);
                }
            """)
            time.sleep(3) # Wait for table reload
        except Exception as e:
            print(f"Error expanding strike range: {e}")

        # Scroll to load all rows (Lazy loading)
        print("Loading all table rows...")
        scroll_element = driver.find_element(By.CSS_SELECTOR, ".dt-scroll-body")
        
        last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_element)
        attempts = 0
        while attempts < 30: # Limit scroll attempts
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_element)
            time.sleep(1)
            new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_element)
            if new_height == last_height:
                break
            last_height = new_height
            attempts += 1
            
        print("Extracting table data...")
        
        # Javascript extraction for speed and reliability
        extraction_script = """
        return (() => {
            const rows = document.querySelectorAll('.dt-scroll-body tbody tr');
            const data = [];
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 20) {
                    // Indices based on analysis:
                    // 0: Ticker (Modelo) -> BOVAB100
                    // 1: FM (Vencimento) -> 20/02/2026
                    // 3: Tipo -> CALL / PUT
                    // 6: Strike -> 100,00
                    // 14: Vol. Impl. (%) -> 35,4
                    // 21: Cob
                    // 22: Trav
                    // 23: Descob
                    
                    const ticker = cells[0].innerText.trim();
                    const expiry = cells[1].innerText.trim();
                    const type_raw = cells[3].innerText.trim();
                    const strike_raw = cells[6].innerText.trim();
                    const iv_raw = cells[14].innerText.trim();
                    
                    // Open Interest components
                    const cob = cells[21].innerText.trim();
                    const trav = cells[22].innerText.trim();
                    const descob = cells[23].innerText.trim();
                    
                    // Market Price (Last)
                    const last_price = cells[10].innerText.trim();
                    
                    data.push({
                        ticker: ticker,
                        expiry: expiry,
                        type: type_raw,
                        strike: strike_raw,
                        iv: iv_raw,
                        cob: cob,
                        trav: trav,
                        descob: descob,
                        last_price: last_price
                    });
                }
            });
            return data;
        })();
        """
        
        raw_data = driver.execute_script(extraction_script)
        print(f"Extracted {len(raw_data)} rows.")
        return raw_data
        
    except Exception as e:
        print(f"Error extracting data: {e}")
        return []
    finally:
        driver.quit()

def clean_number(val):
    if not val or val == '-': return 0.0
    val = val.replace('.', '').replace(',', '.')
    try:
        return float(val)
    except:
        return 0.0

def parse_opcoes_net_data(raw_data):
    if not raw_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(raw_data)
    
    # Clean numeric columns
    df['strike'] = df['strike'].apply(clean_number)
    df['iv'] = df['iv'].apply(clean_number) / 100.0 # Convert 35.4 to 0.354
    df['market_price'] = df['last_price'].apply(clean_number)
    
    # Calculate Total Open Interest
    df['cob'] = df['cob'].apply(clean_number)
    df['trav'] = df['trav'].apply(clean_number)
    df['descob'] = df['descob'].apply(clean_number)
    df['open_interest'] = df['cob'] + df['trav'] + df['descob']
    
    # Clean Expiry
    # Format usually DD/MM/YYYY
    df['expiry'] = pd.to_datetime(df['expiry'], format='%d/%m/%Y', errors='coerce')
    
    # Normalize Type
    df['type'] = df['type'].str.upper()
    
    return df

if __name__ == "__main__":
    print("Testing Opcoes.net.br Scraper...")
    raw = fetch_opcoes_net_data()
    df = parse_opcoes_net_data(raw)
    print(f"\nTotal Options: {len(df)}")
    print(df.head())
    print("\nSample with positive OI:")
    print(df[df['open_interest'] > 0].head())
