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
            
        # Use DataTables API directly - much more reliable than DOM scraping
        # The API returns the data in the original format, bypassing rendering differences
        extraction_script = """
        return (() => {
            try {
                // Try to use DataTables API directly
                const table = $('table.dataTable').DataTable();
                const allData = table.rows().data().toArray();
                
                // Column mapping (based on known structure):
                // 0: Ticker, 1: Tipo, 2: F.M., 3: Mod., 4: Strike,
                // 5: A/I/OTM, 6: Dist.%, 7: Último, 8: Var.%,
                // 9: Data/Hora, 10: Núm.Neg., 11: Vol.Fin., 12: Vol.Impl.%,
                // 13-18: Greeks, 19: Coberto, 20: Travado, 21: Descob.
                
                const results = [];
                for (const row of allData) {
                    if (row.length > 20) {
                        const ticker = String(row[0] || '').trim();
                        // Skip if not a valid ticker
                        if (!ticker.match(/^[A-Z]{4,5}/)) continue;
                        
                        results.push({
                            ticker: ticker,
                            type: String(row[1] || '').trim(),
                            strike: String(row[4] || '').trim(),
                            last_price: String(row[7] || '').trim(),
                            iv: String(row[12] || '').trim(),
                            cob: String(row[19] || '0').trim(),
                            trav: String(row[20] || '0').trim(),
                            descob: String(row[21] || '0').trim()
                        });
                    }
                }
                return results;
                
            } catch(e) {
                // Fallback to DOM scraping if DataTables API not available
                console.log('DataTables API failed, using DOM fallback:', e);
                
                const rows = document.querySelectorAll('.dt-scroll-body tbody tr');
                const data = [];
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length > 20) {
                        // Use fixed indices as last resort
                        const ticker = cells[0].innerText.trim();
                        if (!ticker.match(/^[A-Z]{4,5}/)) return;
                        
                        data.push({
                            ticker: ticker,
                            type: cells[1].innerText.trim(),
                            strike: cells[4].innerText.trim(),
                            last_price: cells[7].innerText.trim(),
                            iv: cells[12].innerText.trim(),
                            cob: cells[19].innerText.trim() || '0',
                            trav: cells[20].innerText.trim() || '0',
                            descob: cells[21].innerText.trim() || '0'
                        });
                    }
                });
                return data;
            }
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
    
    # Mark invalid market prices (0 or negative are invalid for option prices)
    df['market_price'] = df['market_price'].apply(lambda x: x if x > 0 else None)
    
    # Mark invalid IV (0% means no IV data)
    df['iv'] = df['iv'].apply(lambda x: x if x > 0.001 else None)
    
    # Calculate Total Open Interest
    df['cob'] = df['cob'].apply(clean_number)
    df['trav'] = df['trav'].apply(clean_number)
    df['descob'] = df['descob'].apply(clean_number)
    df['open_interest'] = (df['cob'] + df['trav'] + df['descob']).astype(int)
    
    # Extract expiry from ticker code
    # BOVA options use: BOVA[A-L] for calls (Jan-Dec), BOVA[M-X] for puts (Jan-Dec)
    # Weekly options have W[1-5] suffix, e.g., BOVAB158W4
    # We need to map the month letter + year to actual dates
    def extract_expiry_from_ticker(ticker):
        """Extract expiry date from Brazilian option ticker."""
        if not ticker or len(ticker) < 5:
            return None
        
        # Standard format: BASE + MONTH_LETTER + STRIKE + optional WEEK
        # e.g., BOVAB158 = BOVA11 Call February Strike ~158
        #       BOVAN120 = BOVA11 Put February Strike ~120
        #       BOVAB158W4 = Weekly expiry (4th week)
        
        # Month codes: A-L for Calls (Jan-Dec), M-X for Puts (Jan-Dec)
        call_months = 'ABCDEFGHIJKL'
        put_months = 'MNOPQRSTUVWX'
        
        # Find the month letter (should be after the base ticker)
        # BOVA is 4 chars, so month is at position 4
        if len(ticker) < 5:
            return None
            
        month_char = ticker[4].upper()
        
        # Determine month
        if month_char in call_months:
            month = call_months.index(month_char) + 1
        elif month_char in put_months:
            month = put_months.index(month_char) + 1
        else:
            return None
        
        # Assume current year or next year if month has passed
        from datetime import datetime
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        if month < current_month:
            year = current_year + 1
        else:
            year = current_year
        
        # Check for weekly suffix (W1, W2, etc.)
        is_weekly = 'W' in ticker
        if is_weekly:
            # Weekly options expire on Fridays of the specified week
            # W1 = 1st Friday, W2 = 2nd Friday, etc.
            try:
                week_num = int(ticker.split('W')[-1][0])
                # Find the Nth Friday of the month
                import calendar
                first_day = datetime(year, month, 1)
                # Find first Friday
                first_friday = 1 + (4 - first_day.weekday()) % 7
                expiry_day = first_friday + (week_num - 1) * 7
                # Clamp to valid range
                max_day = calendar.monthrange(year, month)[1]
                expiry_day = min(expiry_day, max_day)
                return datetime(year, month, expiry_day)
            except:
                pass
        
        # Standard monthly expiry (3rd Friday of the month)
        import calendar
        first_day = datetime(year, month, 1)
        first_friday = 1 + (4 - first_day.weekday()) % 7
        third_friday = first_friday + 14
        
        return datetime(year, month, third_friday)
    
    df['expiry'] = df['ticker'].apply(extract_expiry_from_ticker)
    
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
