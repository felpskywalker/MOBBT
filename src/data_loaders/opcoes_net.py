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
    """Create and configure Chrome WebDriver.
    
    Supports both:
    - Local development with webdriver-manager
    - Streamlit Cloud with system-installed Chromium
    """
    import shutil
    import os
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Use headless mode for production
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    # Check for system Chromium (Streamlit Cloud / Linux)
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable'
    ]
    
    chromedriver_paths = [
        '/usr/bin/chromedriver',
        '/usr/lib/chromium/chromedriver',
        '/usr/lib/chromium-browser/chromedriver'
    ]
    
    # Find Chromium binary
    chromium_binary = None
    for path in chromium_paths:
        if os.path.exists(path):
            chromium_binary = path
            break
    
    # Find ChromeDriver
    chromedriver_path = None
    for path in chromedriver_paths:
        if os.path.exists(path):
            chromedriver_path = path
            break
    
    # Also check with shutil.which
    if not chromedriver_path:
        chromedriver_path = shutil.which('chromedriver')
    
    if chromium_binary:
        chrome_options.binary_location = chromium_binary
        print(f"[SELENIUM] Using system Chromium: {chromium_binary}")
    
    if chromedriver_path:
        print(f"[SELENIUM] Using system ChromeDriver: {chromedriver_path}")
        service = Service(chromedriver_path)
    else:
        # Fallback to webdriver-manager (local development)
        print("[SELENIUM] Using webdriver-manager for ChromeDriver")
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
        
        # 1. Select ALL maturities (Vencimentos) using JavaScript for reliability
        print("Selecting all maturities...")
        try:
            # Use JavaScript to select all maturity checkboxes
            driver.execute_script("""
                // Select all maturity checkboxes
                var checkboxes = document.querySelectorAll('#grade-vencimentos-dates input[type="checkbox"]');
                console.log('Found ' + checkboxes.length + ' maturity checkboxes');
                checkboxes.forEach(function(cb) {
                    if (!cb.checked) {
                        cb.click();
                    }
                });
            """)
            time.sleep(2)
            
            # Trigger grid reload
            driver.execute_script("""
                try {
                    if (typeof gradeOpcoes !== 'undefined' && gradeOpcoes.CarregarGrade) {
                        gradeOpcoes.CarregarGrade();
                    }
                } catch(e) {
                    console.log('Could not reload grid: ' + e);
                }
            """)
            time.sleep(3)  # Wait for table reload
        except Exception as e:
            print(f"Error selecting maturities: {e}")
        
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
            
        # DOM Extraction with CORRECT indices for multi-expiry table
        # When multiple expiries are selected, table adds "Vencimento" and "Dias úteis" columns
        # Indices verified via browser inspection:
        # 0: Ticker, 1: Vencimento (Expiry date), 2: Dias úteis, 3: Tipo (CALL/PUT)
        # 6: Strike, 9: Último (Price), 10: Var.(%), 14: Vol.Impl. (IV)
        # 15: Delta, 16: Gamma, 17: Theta($), 18: Theta(%), 19: Vega
        # 21: Cob, 22: Trav, 23: Descob
        extraction_script = """
        return (() => {
            const rows = document.querySelectorAll('.dt-scroll-body tbody tr');
            const data = [];
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 20) {
                    // Correct indices for multi-expiry table:
                    const ticker = cells[0].innerText.trim();
                    const expiry = cells[1].innerText.trim();
                    const type_raw = cells[3].innerText.trim();
                    const strike_raw = cells[6].innerText.trim();
                    const iv_raw = cells[14].innerText.trim();
                    const last_price = cells[9].innerText.trim();  // Index 9 = Último
                    
                    // Greeks from the site
                    const delta_raw = cells[15].innerText.trim();
                    const gamma_raw = cells[16].innerText.trim();
                    
                    // Open Interest components
                    const cob = cells[21].innerText.trim();
                    const trav = cells[22].innerText.trim();
                    const descob = cells[23].innerText.trim();
                    
                    // Only add if ticker looks valid
                    if (ticker && ticker.match(/^[A-Z]{4,5}/)) {
                        data.push({
                            ticker: ticker,
                            expiry: expiry,
                            type: type_raw,
                            strike: strike_raw,
                            iv: iv_raw,
                            delta: delta_raw,
                            gamma: gamma_raw,
                            cob: cob,
                            trav: trav,
                            descob: descob,
                            last_price: last_price
                        });
                    }
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
    """Parse raw scraped data into a clean DataFrame."""
    if not raw_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(raw_data)
    
    # Clean numeric columns
    df['strike'] = df['strike'].apply(clean_number)
    df['market_price'] = df['last_price'].apply(clean_number)
    
    # Clean IV - handle percentage format
    df['iv'] = df['iv'].apply(clean_number) / 100.0  # Convert 35.4 to 0.354
    
    # Clean Greeks from site (gamma and delta)
    if 'gamma' in df.columns:
        df['gamma_site'] = df['gamma'].apply(clean_number)
        # Mark invalid gamma (0 means no data)
        df['gamma_site'] = df['gamma_site'].apply(lambda x: x if x > 0 else None)
        print(f"[DEBUG] Gamma from site - valid: {df['gamma_site'].notna().sum()}/{len(df)}")
    
    if 'delta' in df.columns:
        df['delta_site'] = df['delta'].apply(clean_number)
    
    # Mark invalid market prices (0 or negative are invalid for option prices)
    df['market_price'] = df['market_price'].apply(lambda x: x if x > 0 else None)
    
    # Mark invalid IV (0% means no IV data)
    df['iv'] = df['iv'].apply(lambda x: x if x > 0.001 else None)
    
    # Calculate Total Open Interest
    df['cob'] = df['cob'].apply(clean_number)
    df['trav'] = df['trav'].apply(clean_number)
    df['descob'] = df['descob'].apply(clean_number)
    df['open_interest'] = (df['cob'] + df['trav'] + df['descob']).astype(int)
    
    # Parse expiry date from page data (format: DD/MM/YYYY)
    df['expiry'] = pd.to_datetime(df['expiry'], format='%d/%m/%Y', errors='coerce')
    
    # Normalize Type - handle various formats
    df['type'] = df['type'].str.strip().str.upper()
    
    # Debug: print unique types found
    print(f"[DEBUG] Unique type values: {df['type'].unique().tolist()}")
    print(f"[DEBUG] Sample strikes: {df['strike'].head().tolist()}")
    print(f"[DEBUG] Rows before filter: {len(df)}")
    
    # Filter out rows without valid strike
    df = df[df['strike'] > 0]
    print(f"[DEBUG] Rows after strike filter: {len(df)}")
    
    # More flexible type matching - check if 'CALL' or 'PUT' is contained
    def normalize_type(t):
        t = str(t).upper().strip()
        if 'CALL' in t or t == 'C':
            return 'CALL'
        elif 'PUT' in t or t == 'P':
            return 'PUT'
        return t
    
    df['type'] = df['type'].apply(normalize_type)
    df = df[df['type'].isin(['CALL', 'PUT'])]
    print(f"[DEBUG] Rows after type filter: {len(df)}")
    
    return df

if __name__ == "__main__":
    print("Testing Opcoes.net.br Scraper...")
    raw = fetch_opcoes_net_data()
    df = parse_opcoes_net_data(raw)
    print(f"\nTotal Options: {len(df)}")
    print(df.head())
    print("\nSample with positive OI:")
    print(df[df['open_interest'] > 0].head())
