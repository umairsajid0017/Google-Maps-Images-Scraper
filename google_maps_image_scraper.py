import os
import time
import logging
import argparse
import requests
import csv
import json
import threading
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, unquote
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("gmaps_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_csv_file(self, location_name):
        """
        Create a CSV file for storing image URLs
        
        Args:
            location_name (str): Name of the location
            
        Returns:
            str: Path to the created CSV file
        """
        location_dir = os.path.join(self.download_dir, self._sanitize_filename(location_name))
        if not os.path.exists(location_dir):
            os.makedirs(location_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"{self._sanitize_filename(location_name)}_urls_{timestamp}.csv"
        csv_path = os.path.join(location_dir, csv_filename)
        
        # Create the CSV file with headers
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['index', 'image_url', 'timestamp'])
            
        logger.info(f"Created CSV file: {csv_path}")
        return csv_path
        
def save_url_to_csv(self, csv_path, url, index):
    """
    Save a URL to the CSV file in a thread-safe manner
    
    Args:
        csv_path (str): Path to the CSV file
        url (str): Image URL to save
        index (int): Index of the URL
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        with self.csv_lock:  # Use lock to prevent multiple threads from writing simultaneously
            with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                csv_writer = csv.writer(csvfile)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                csv_writer.writerow([index, url, timestamp])
                
                # Flush after each write to ensure real-time updates
                csvfile.flush()
                
                # Log every 10th URL or first few URLs
                if index <= 5 or index % 10 == 0:
                    print(f"Saved URL #{index} to CSV")
                    logger.info(f"Saved URL #{index} to CSV: {url[:50]}...")
        return True
    except Exception as e:
        logger.error(f"Error saving URL to CSV: {str(e)}")
        return False
    
class GoogleMapsImageScraper:
    def __init__(self, headless=True, download_dir="downloaded_images", timeout=30, save_csv=True):
        """
        Initialize the Google Maps Image Scraper
        
        Args:
            headless (bool): Run browser in headless mode
            download_dir (str): Directory to save downloaded images
            timeout (int): Default timeout for WebDriverWait
            save_csv (bool): Whether to save image URLs to CSV
        """
        self.download_dir = download_dir
        self.timeout = timeout
        self.save_csv = save_csv
        self.csv_lock = threading.Lock()  # Lock for thread-safe CSV operations
        
        # Create download directory if it doesn't exist
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
            
        # Setup Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")  # modern headless: faster & more accurate
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        # Performance: disable unused browser subsystems
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--metrics-recording-only")
        chrome_options.add_argument("--mute-audio")
        # User agent
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        
        # Initialize WebDriver with multiple fallback approaches
        self.driver = None
        initialization_error = None
        
        # Approach 1: Try with webdriver-manager but fix the path
        try:
            chrome_driver_path = ChromeDriverManager().install()
            
            # Fix the common webdriver-manager path issue
            import platform
            is_windows = platform.system() == "Windows"
            exe_ext = ".exe" if is_windows else ""
            
            if "THIRD_PARTY_NOTICES" in chrome_driver_path or (is_windows and not chrome_driver_path.endswith(".exe")):
                # Try to find the actual chromedriver in the same directory
                import glob
                driver_dir = os.path.dirname(chrome_driver_path)
                possible_paths = glob.glob(os.path.join(driver_dir, f"**/chromedriver{exe_ext}"), recursive=True)
                if possible_paths:
                    chrome_driver_path = possible_paths[0]
                    logger.info(f"Fixed ChromeDriver path to: {chrome_driver_path}")
                else:
                    # Try parent directories
                    parent_dir = os.path.dirname(driver_dir)
                    possible_paths = glob.glob(os.path.join(parent_dir, f"**/chromedriver{exe_ext}"), recursive=True)
                    if possible_paths:
                        chrome_driver_path = possible_paths[0]
                        logger.info(f"Found ChromeDriver in parent directory: {chrome_driver_path}")
                    else:
                        raise Exception(f"Could not locate chromedriver{exe_ext}")
            
            self.driver = webdriver.Chrome(
                service=Service(chrome_driver_path),
                options=chrome_options
            )
            self.driver.maximize_window()
            logger.info("WebDriver initialized successfully with fixed path")
            
        except Exception as e:
            initialization_error = str(e)
            logger.warning(f"First WebDriver approach failed: {initialization_error}")
            
            # Approach 2: Try without webdriver-manager (use Chrome from PATH)
            try:
                logger.info("Trying WebDriver initialization without webdriver-manager...")
                self.driver = webdriver.Chrome(options=chrome_options)
                self.driver.maximize_window()
                logger.info("WebDriver initialized successfully without webdriver-manager")
                
            except Exception as e2:
                initialization_error = str(e2)
                logger.warning(f"Second WebDriver approach failed: {initialization_error}")
                
                # Approach 3: Try downloading ChromeDriver manually
                try:
                    logger.info("Attempting manual ChromeDriver download...")
                    manual_driver_path = self._download_chromedriver_manually()
                    
                    if manual_driver_path and os.path.exists(manual_driver_path):
                        self.driver = webdriver.Chrome(
                            service=Service(manual_driver_path),
                            options=chrome_options
                        )
                        self.driver.maximize_window()
                        logger.info("WebDriver initialized successfully with manual ChromeDriver")
                    else:
                        raise Exception("Manual ChromeDriver download failed")
                        
                except Exception as e3:
                    initialization_error = str(e3)
                    logger.error(f"All WebDriver initialization approaches failed. Last error: {initialization_error}")
                    raise WebDriverException(f"Failed to initialize WebDriver after all attempts. Error: {initialization_error}")
        
        if self.driver is None:
            raise WebDriverException(f"Failed to initialize WebDriver. Error: {initialization_error}")
            
    def create_csv_file(self, location_name):
        """
        Create a CSV file for storing image URLs
        
        Args:
            location_name (str): Name of the location
            
        Returns:
            str: Path to the created CSV file
        """
        location_dir = os.path.join(self.download_dir, self._sanitize_filename(location_name))
        if not os.path.exists(location_dir):
            os.makedirs(location_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"{self._sanitize_filename(location_name)}_urls_{timestamp}.csv"
        csv_path = os.path.join(location_dir, csv_filename)
        
        # Create the CSV file with headers
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['index', 'image_url', 'timestamp'])
            
        logger.info(f"Created CSV file: {csv_path}")
        return csv_path
        
    def save_url_to_csv(self, csv_path, url, index):
        """
        Save a URL to the CSV file in a thread-safe manner
        
        Args:
            csv_path (str): Path to the CSV file
            url (str): Image URL to save
            index (int): Index of the URL
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            with self.csv_lock:  # Use lock to prevent multiple threads from writing simultaneously
                with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                    csv_writer = csv.writer(csvfile)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    csv_writer.writerow([index, url, timestamp])
                    
                    # Flush after each write to ensure real-time updates
                    csvfile.flush()
                    
                    # Log every 10th URL or first few URLs
                    if index <= 5 or index % 10 == 0:
                        print(f"Saved URL #{index} to CSV")
                        logger.info(f"Saved URL #{index} to CSV: {url[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Error saving URL to CSV: {str(e)}")
            return False
        
    def _download_chromedriver_manually(self):
        """
        Manually download ChromeDriver as a fallback
        
        Returns:
            str: Path to chromedriver executable or None if failed
        """
        try:
            import requests
            import zipfile
            import platform
            
            # Create drivers directory if it doesn't exist
            drivers_dir = os.path.join(os.getcwd(), "drivers")
            if not os.path.exists(drivers_dir):
                os.makedirs(drivers_dir)
            
            # Check if we already have a working chromedriver
            chromedriver_path = os.path.join(drivers_dir, "chromedriver.exe")
            if os.path.exists(chromedriver_path):
                logger.info("Found existing chromedriver.exe")
                return chromedriver_path
            
            logger.info("Downloading ChromeDriver manually...")
            
            # Get the appropriate ChromeDriver version
            # Using a stable version that should work
            version = "131.0.6778.87"  # A stable version
            
            # Determine architecture
            if platform.machine().endswith('64'):
                url = f"https://storage.googleapis.com/chrome-for-testing-public/{version}/win64/chromedriver-win64.zip"
                folder_name = "chromedriver-win64"
            else:
                url = f"https://storage.googleapis.com/chrome-for-testing-public/{version}/win32/chromedriver-win32.zip"
                folder_name = "chromedriver-win32"
            
            # Download the zip file
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            zip_path = os.path.join(drivers_dir, "chromedriver.zip")
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            # Extract the zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(drivers_dir)
            
            # Move the chromedriver.exe to the drivers directory
            extracted_driver = os.path.join(drivers_dir, folder_name, "chromedriver.exe")
            if os.path.exists(extracted_driver):
                # Move to drivers directory root
                final_path = os.path.join(drivers_dir, "chromedriver.exe")
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(extracted_driver, final_path)
                
                # Clean up
                os.remove(zip_path)
                import shutil
                shutil.rmtree(os.path.join(drivers_dir, folder_name))
                
                logger.info(f"ChromeDriver downloaded successfully to: {final_path}")
                return final_path
            else:
                logger.error(f"Could not find chromedriver.exe in extracted files")
                return None
                
        except Exception as e:
            logger.error(f"Failed to download ChromeDriver manually: {str(e)}")
            return None
            
    def _is_in_gallery_view(self):
        """
        Check if we're currently in the gallery view
        
        Returns:
            bool: True if we're in gallery view, False otherwise
        """
        try:
            # Check for elements that indicate we're in gallery view
            gallery_indicators = [
                "button[aria-label='Next photo'], button[aria-label='Next']",
                "div.m6QErb.DxyBCb.kA9KIf.dS8AEf",  # Gallery container
                "div.aomaEc, button.aomaEc",  # Next button
                "div.U7izfe",  # Photo view container
                "div.YbQ5dc"   # Another gallery container class
            ]
            
            for indicator in gallery_indicators:
                if len(self.driver.find_elements(By.CSS_SELECTOR, indicator)) > 0:
                    return True
                    
            # Check for JavaScript gallery state
            try:
                in_gallery = self.driver.execute_script("""
                    return (
                        document.querySelector("div[role='dialog'][aria-label*='photo']") !== null ||
                        document.querySelector("div.m6QErb.DxyBCb.kA9KIf.dS8AEf") !== null
                    );
                """)
                
                if in_gallery:
                    return True
            except Exception:
                pass
                
            return False
        except Exception as e:
            logger.debug(f"Error checking gallery view: {str(e)}")
            return False

    def search_location(self, location_name):
        """
        Search for a location on Google Maps
        
        Args:
            location_name (str): Name of the location to search
            
        Returns:
            bool: True if search was successful, False otherwise
        """
        try:
            # Navigate to Google Maps
            self.driver.get("https://www.google.com/maps")
            logger.info(f"Searching for location: {location_name}")
            
            # Brief buffer for page init
            time.sleep(1)
            
            # Wait for the search box to be present and click on it
            search_box = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#searchboxinput, input[name='q'], input[aria-label*='Search']"))
            )
            search_box.clear()
            search_box.send_keys(location_name)
            search_box.send_keys(Keys.ENTER)
            
            # Short delay after search to allow results to load
            # Short delay after search to allow results to load (2s is safe minimum)
            time.sleep(2)
            
            # Check if we're directly on the place page (when there's a direct match)
            try:
                place_header = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf, div.fontHeadlineLarge, div[role='heading']"))
                )
                if place_header:
                    logger.info(f"Direct match found: {place_header.text}")
                    return True
            except (TimeoutException, NoSuchElementException):
                pass
                
            # Try to find and click on the first result with multiple approaches
            selectors_to_try = [
                # Current Google Maps result card selectors
                "div.Nv2PK a.hfpxzc",
                "a.hfpxzc",
                "div.Nv2PK",
                # Backup selectors
                "div[jsaction*='placecard']",
                "div[data-item-id]",
                "div[role='article']",
                "a[jsaction*='placepage']",
                "div.section-result-content",
            ]
            
            for selector in selectors_to_try:
                try:
                    element = WebDriverWait(self.driver, 4).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.3)
                    self.driver.execute_script("arguments[0].click();", element)
                    logger.info(f"Location found and clicked with selector: {selector}")
                    time.sleep(1.5)  # Wait for place page to load
                    return True
                except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
                    continue
            
            # JS fallback: grab the very first clickable result card in the DOM
            try:
                clicked = self.driver.execute_script("""
                    const first = document.querySelector(
                        'div.Nv2PK a.hfpxzc, a.hfpxzc, div[data-item-id] a, div.Nv2PK'
                    );
                    if (first) { first.click(); return true; }
                    return false;
                """)
                if clicked:
                    logger.info("Clicked first result via JS fallback")
                    time.sleep(1.5)
                    return True
            except Exception:
                pass

            
            # If we still haven't found a result, check if we're already on a place page
            # Sometimes Google Maps navigates directly to the place page for exact matches
            try:
                # Check for any place page indicators
                if any([
                    len(self.driver.find_elements(By.CSS_SELECTOR, "button[jsaction*='pane.rating.category']")) > 0,
                    len(self.driver.find_elements(By.CSS_SELECTOR, "button[data-item-id='photos'], button[aria-label*='photo']")) > 0,
                    len(self.driver.find_elements(By.CSS_SELECTOR, "div.RcCsl")) > 0
                ]):
                    logger.info("Already on a place page, continuing...")
                    return True
            except Exception:
                pass
                
            logger.warning(f"No search results found for '{location_name}' after trying all selectors")
            return False
                
        except Exception as e:
            logger.error(f"Error searching for location: {str(e)}")
            return False

    def open_photos_section(self):
        """
        Open the photos section of the location
        
        Returns:
            bool: True if photos section was opened, False otherwise
        """
        try:
            # Short delay to ensure page is fully loaded
            time.sleep(1)
            
            # Try multiple approaches to find and click the photos section
            selectors_to_try = [
                # Direct photo buttons
                "button[aria-label*='photo' i], button[data-item-id*='photo' i], a[aria-label*='photo' i], a[data-item-id*='photo' i]",
                # Photo section links
                "a[data-tab='images'], a[data-tab='photos']",
                # Text-based photo buttons
                "//button[.//div[contains(translate(text(), 'PHOTOS', 'photos'), 'photos')]]",
                "//a[.//div[contains(translate(text(), 'PHOTOS', 'photos'), 'photos')]]",
                # Photo icon buttons
                "button[jsaction*='photo'], button[jsaction*='image']",
                # Photo count elements
                "span.YbCJSd, div.bJP2oh, div.Yr7JMd",
                # Photo thumbnails directly
                "div.U39Pmb img, div.AdyRSe"
            ]
            
            for selector in selectors_to_try:
                try:
                    # Check if we need to use XPath
                    if selector.startswith("//"):
                        elements = self.driver.find_elements(By.XPATH, selector)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        
                    if elements:
                        # Try clicking the first element that's visible and enabled
                        for element in elements:
                            if element.is_displayed():
                                # Scroll element into view
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(0.5)
                                
                                # Try direct click
                                try:
                                    element.click()
                                    logger.info(f"Photos section opened using selector: {selector}")
                                    time.sleep(1.5)  # Wait for photos to load
                                    return True
                                except ElementClickInterceptedException:
                                    # Try JavaScript click if direct click fails
                                    try:
                                        self.driver.execute_script("arguments[0].click();", element)
                                        logger.info(f"Photos section opened using JavaScript click with selector: {selector}")
                                        time.sleep(1.5)
                                        return True
                                    except Exception:
                                        continue
                except Exception as e:
                    logger.debug(f"Failed with selector {selector}: {str(e)}")
                    continue
            
            # Check if we're already in the photos section
            try:
                photo_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.loaded-media-item-container, div[role='img'], img.qaFoQ, div.gallery-image-high-res")
                if len(photo_elements) > 0:
                    logger.info("Already in photos section")
                    return True
            except Exception:
                pass
                
            logger.error("Could not open photos section after trying all selectors")
            return False
            
        except Exception as e:
            logger.error(f"Error opening photos section: {str(e)}")
            return False

    def extract_image_urls(self, max_images=None, location_name=None, show_progress=False, callback=None, skip_images=0):
        """
        Extract all image URLs from the photos section
        
        Args:
            max_images (int, optional): Maximum number of images to extract
            location_name (str, optional): Name of the location for CSV
            show_progress (bool): Whether to show detailed progress logging
            callback (callable, optional): Callback function for each new image URL
            skip_images (int): Number of images to skip from start of gallery
            
        Returns:
            list: List of image URLs
        """
        image_urls = set()
        skipped_urls = set()
        images_seen = 0
        last_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 30
        retry_attempts = 3
        
        # Set up CSV if needed
        csv_path = None
        if self.save_csv and location_name:
            csv_path = self.create_csv_file(location_name)
            if show_progress:
                print(f"Creating CSV file at: {csv_path}")
            logger.info(f"Creating CSV file at: {csv_path}")
        
        logger.info("Starting to extract image URLs")
        if show_progress:
            if max_images:
                print(f"Extracting up to {max_images} images...")
            else:
                print(f"Extracting all available images...")
        
        # First check if we need to click on an image to open the gallery
        gallery_attempt = 0
        while not self._is_in_gallery_view() and gallery_attempt < retry_attempts:
            try:
                gallery_attempt += 1
                logger.info(f"Attempting to enter gallery view (attempt {gallery_attempt}/{retry_attempts})")
                
                # Try various selectors for the first image
                selectors_to_try = [
                    "div[role='img'], img.qaFoQ",
                    "div.loaded-media-item-container img",
                    "div.gallery-image-container img",
                    "img.qTegM, img.r7MLu, img.OVwCQd",
                    "div.AdyRSe, div.U39Pmb",
                    # Generic image elements that might be part of the gallery
                    "div.photos-album-container img",
                    "img[src*='googleusercontent']"
                ]
                
                for selector in selectors_to_try:
                    try:
                        elements = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                        )
                        
                        if elements:
                            for element in elements:
                                if not element.is_displayed():
                                    continue
                                    
                                # Scroll into view and click
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(2)  # Increased wait time
                                
                                try:
                                    # Try a fresh reference to the element to avoid stale references
                                    # Re-find the element after scrolling
                                    elements_after_scroll = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                    for el in elements_after_scroll:
                                        if el.is_displayed():
                                            el.click()
                                            logger.info(f"Image clicked to open gallery view using selector: {selector}")
                                            time.sleep(3)  # Wait for gallery to load
                                            break
                                except Exception as e:
                                    logger.debug(f"Direct click failed: {str(e)}")
                                    # Try JavaScript click if direct click fails
                                    try:
                                        self.driver.execute_script("arguments[0].click();", element)
                                        logger.info("Image clicked with JavaScript to open gallery view")
                                        time.sleep(3)
                                        break
                                    except Exception as js_e:
                                        logger.debug(f"JavaScript click failed: {str(js_e)}")
                                        continue
                            
                            # Check if we're now in gallery view
                            if self._is_in_gallery_view():
                                break
                    except Exception as e:
                        logger.debug(f"Error with selector {selector}: {str(e)}")
                        continue
                
                # If we've entered gallery view, break out of retry loop
                if self._is_in_gallery_view():
                    break
                    
                # If not in gallery view after trying all selectors, retry a different approach
                if gallery_attempt < retry_attempts:
                    logger.info(f"Could not enter gallery view, trying alternative approach...")
                    
                    # Try clicking on the "Photos" text link if available
                    try:
                        photo_links = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Photos')] | //span[contains(text(), 'Photos')]")
                        if photo_links:
                            for link in photo_links:
                                if link.is_displayed():
                                    self.driver.execute_script("arguments[0].click();", link)
                                    time.sleep(3)
                                    break
                    except Exception:
                        pass
                    
                    # Try to refresh the page and wait before next attempt
                    try:
                        self.driver.refresh()
                        time.sleep(5)
                    except Exception:
                        pass
                
            except Exception as e:
                logger.warning(f"Error attempting to enter gallery view (attempt {gallery_attempt}): {str(e)}")
                time.sleep(2)
        
        # If we still aren't in gallery view after all retries, use an alternative approach
        if not self._is_in_gallery_view():
            logger.warning("Could not enter gallery view, attempting to extract images directly")
            direct_urls = self._extract_images_direct(csv_path, callback)
            
            # Show progress for direct extraction
            if show_progress and direct_urls:
                for i, url in enumerate(direct_urls, 1):
                    if max_images:
                        print(f"Images Extracted: {i}/{min(max_images, len(direct_urls))}")
                    else:
                        print(f"Images Extracted: {i}")
                    
                    # Save direct URLs to CSV if needed
                    if csv_path:
                        self.save_url_to_csv(csv_path, url, i)
                        
                    # Stop if we've reached max_images
                    if max_images and i >= max_images:
                        break
            
            return direct_urls[:max_images] if max_images else direct_urls
        
        logger.info("Successfully entered gallery view, beginning image extraction")
        
        # Extract images by navigating through the gallery
        consecutive_errors = 0
        max_consecutive_errors = 5
        url_index = 1  # Counter for URLs found
        
        while True:
            try:
                # Try multiple selectors for the current image
                img_selectors = [
                    "img.aIMqZ, div.OhtVzd img",
                    "div.YmEk1d img, img.tK6ULc",
                    "div[role='main'] img[src*='googleusercontent']",
                    "div.gallery-image-high-res img",
                    "img[style*='transform']",  # Often the main image has transform styles
                    "div.gallery-image-container img"
                ]
                
                found_image = False
                for selector in img_selectors:
                    try:
                        # Use a very short timeout since we already slept after clicking next
                        wait = WebDriverWait(self.driver, 0.4)
                        img_elements = wait.until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                        )
                        
                        for img_element in img_elements:
                            if not img_element.is_displayed():
                                continue
                                
                            # Get image URL with retry for stale references
                            for retry in range(3):
                                try:
                                    current_url = img_element.get_attribute("src")
                                    break
                                except StaleElementReferenceException:
                                    if retry < 2:  # Last retry
                                        logger.debug(f"Stale reference when getting src, retry {retry+1}/3")
                                        # Re-find element
                                        wait = WebDriverWait(self.driver, 0.4)
                                        img_elements = wait.until(
                                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                                        )
                                        if img_elements:
                                            img_element = img_elements[0]
                                        time.sleep(0.2)
                                    else:
                                        current_url = None
                                except Exception:
                                    current_url = None
                                    break
                            
                            # Add high-resolution version of image URL
                            if current_url and "googleusercontent.com" in current_url:
                                # Transform URL to get the highest resolution (w0-h0-k-no gets original image size with no restrictions)
                                high_res_url = re.sub(r'=(w\d+-h\d+|w\d+|h\d+|s\d+)(.*)', '=w0-h0-k-no', current_url)
                                
                                # Only add if it's a new URL
                                if high_res_url not in image_urls and high_res_url not in skipped_urls:
                                    images_seen += 1
                                    if images_seen <= skip_images:
                                        # Skip this image! We don't save it or fire callback
                                        found_image = True
                                        consecutive_errors = 0
                                        break
 
                                    accepted = True
                                    if callback:
                                        accepted = callback(high_res_url)
                                    
                                    if accepted:
                                        image_urls.add(high_res_url)
                                        logger.debug(f"Added image URL: {high_res_url}")
                                        
                                        # Show progress
                                        if show_progress:
                                            if max_images:
                                                print(f"Images Extracted: {url_index}/{max_images}")
                                            else:
                                                print(f"Images Extracted: {url_index}")
                                        
                                        # Save URL to CSV in real-time
                                        if csv_path:
                                            self.save_url_to_csv(csv_path, high_res_url, url_index)
                                            
                                        url_index += 1
                                        found_image = True
                                        consecutive_errors = 0  # Reset error counter on success
                                        break
                                    else:
                                        skipped_urls.add(high_res_url)
                                        found_image = True
                                        consecutive_errors = 0
                                        break
                    except Exception as e:
                        logger.debug(f"Error with image selector {selector}: {str(e)}")
                        continue
                        
                if not found_image:
                    # Try JavaScript approach if no images found with regular selectors
                    try:
                        # Get all images from the page using JavaScript
                        all_imgs = self.driver.execute_script("""
                            return Array.from(document.querySelectorAll('img'))
                                .filter(img => img.src && img.src.includes('googleusercontent'))
                                .map(img => img.src);
                        """)
                        
                        for url in all_imgs:
                            if "googleusercontent.com" in url:
                                # Transform URL to get the highest resolution (w0-h0-k-no gets original image size with no restrictions)
                                high_res_url = re.sub(r'=(w\d+-h\d+|w\d+|h\d+|s\d+)(.*)', '=w0-h0-k-no', url)
                                
                                # Only add if it's a new URL
                                if high_res_url not in image_urls and high_res_url not in skipped_urls:
                                    images_seen += 1
                                    if images_seen <= skip_images:
                                        # Skip this image!
                                        found_image = True
                                        consecutive_errors = 0
                                        continue
 
                                    accepted = True
                                    if callback:
                                        accepted = callback(high_res_url)
                                    
                                    if accepted:
                                        image_urls.add(high_res_url)
                                        
                                        # Show progress
                                        if show_progress:
                                            if max_images:
                                                print(f"Images Extracted: {url_index}/{max_images}")
                                            else:
                                                print(f"Images Extracted: {url_index}")
                                        
                                        # Save URL to CSV in real-time
                                        if csv_path:
                                            self.save_url_to_csv(csv_path, high_res_url, url_index)
                                            
                                        url_index += 1
                                        found_image = True
                                        consecutive_errors = 0  # Reset error counter on success
                                    else:
                                        skipped_urls.add(high_res_url)
                                        found_image = True
                                        consecutive_errors = 0
                    except Exception as e:
                        logger.debug(f"JavaScript image extraction failed: {str(e)}")
                
                if not found_image:
                    consecutive_errors += 1
                    logger.warning(f"No image found on this page (consecutive errors: {consecutive_errors}/{max_consecutive_errors})")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.warning("Too many consecutive errors, stopping extraction")
                        break
                
                # Check if we've reached the max number of images
                if max_images and len(image_urls) >= max_images:
                    logger.info(f"Reached maximum number of images: {max_images}")
                    if show_progress:
                        print(f"Reached maximum limit of {max_images} images")
                    break
                
                # Try different selectors for the next button
                next_button_selectors = [
                    "button[aria-label='Next photo'], button[aria-label='Next']",
                    "[jsaction*='pane.nextbatch']",
                    "button.mL3Fgc, button[aria-label*='next']",
                    "button.tit8B, button.aomaEc",
                    "//button[contains(@aria-label, 'Next')]"  # XPath for "Next" in various languages
                ]
                
                next_clicked = False
                for selector in next_button_selectors:
                    try:
                        if selector.startswith("//"):  # XPath selector
                            next_buttons = WebDriverWait(self.driver, 0.4).until(
                                EC.presence_of_all_elements_located((By.XPATH, selector))
                            )
                        else:  # CSS selector
                            next_buttons = WebDriverWait(self.driver, 0.4).until(
                                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                            )
                            
                        if next_buttons:
                            for btn in next_buttons:
                                if not btn.is_displayed():
                                    continue
                                
                                try:
                                    # Scroll button into view first
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                                    time.sleep(0.2)
                                    
                                    # Try to click with fresh reference after scrolling
                                    if selector.startswith("//"):
                                        refreshed_buttons = self.driver.find_elements(By.XPATH, selector)
                                    else:
                                        refreshed_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                    
                                    for refreshed_btn in refreshed_buttons:
                                        if refreshed_btn.is_displayed():
                                            refreshed_btn.click()
                                            next_clicked = True
                                            time.sleep(0.7)  # reduced: image usually loads < 1s
                                            break
                                except ElementClickInterceptedException:
                                    # Try JavaScript click
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    next_clicked = True
                                    time.sleep(0.7)
                                    break
                                except StaleElementReferenceException:
                                    logger.debug("Stale element when clicking next, retrying with fresh elements")
                                    continue
                        
                        if next_clicked:
                            break
                    except Exception as e:
                        logger.debug(f"Error with next button selector {selector}: {str(e)}")
                        continue
                
                if not next_clicked:
                    logger.info("Could not find or click next button, assuming end of gallery")
                    if show_progress:
                        print(f"Reached end of gallery - no more images available")
                    break
                
                # Check if we're still finding new images
                if len(image_urls) == last_count:
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0
                    
                last_count = len(image_urls)
                
                # If we're not finding new images after multiple attempts, we've likely reached the end
                if scroll_attempts >= max_scroll_attempts:
                    logger.info("No new images found after multiple attempts, stopping extraction")
                    if show_progress:
                        print(f"No new images found - extraction complete")
                    break
                    
            except StaleElementReferenceException:
                logger.warning("Stale element reference, retrying...")
                consecutive_errors += 1
                time.sleep(0.5)
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning("Too many consecutive stale element errors, stopping extraction")
                    break
            except Exception as e:
                logger.error(f"Unexpected error during image extraction: {str(e)}")
                consecutive_errors += 1
                time.sleep(0.5)
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning("Too many consecutive errors, stopping extraction")
                    break
                
        logger.info(f"Extracted {len(image_urls)} unique image URLs")
        
        if csv_path:
            logger.info(f"Image URLs saved to: {csv_path}")
            
        return list(image_urls)
        
    def _extract_images_direct(self, csv_path=None, callback=None):
        """
        Alternative method to extract images directly from the page without gallery navigation
        
        Args:
            csv_path (str, optional): Path to CSV file to save URLs
            callback (callable, optional): Callback function for each new image URL
            
        Returns:
            list: List of image URLs
        """
        image_urls = set()
        skipped_urls = set()
        url_index = 1  # For CSV indexing
        logger.info("Attempting to extract images directly from the page")
        
        try:
            # First try to get all images with src containing googleusercontent
            js_images = self.driver.execute_script("""
                return Array.from(document.querySelectorAll('img'))
                    .filter(img => img.src && img.src.includes('googleusercontent'))
                    .map(img => img.src);
            """)
            
            for url in js_images:
                if "googleusercontent.com" in url:
                    # Transform URL to get the highest resolution (w0-h0-k-no gets original image size with no restrictions)
                    high_res_url = re.sub(r'=(w\d+-h\d+|w\d+|h\d+|s\d+)(.*)', '=w0-h0-k-no', url)
                    if high_res_url not in image_urls and high_res_url not in skipped_urls:
                        accepted = True
                        if callback:
                            accepted = callback(high_res_url)
                        if accepted:
                            image_urls.add(high_res_url)
                            # Save to CSV if needed
                            if csv_path:
                                self.save_url_to_csv(csv_path, high_res_url, url_index)
                                url_index += 1
                        else:
                            skipped_urls.add(high_res_url)
            
            logger.info(f"Found {len(image_urls)} images using JavaScript extraction")
            
            # If JavaScript approach didn't find enough images, try selectors
            if len(image_urls) < 5:
                image_selectors = [
                    "img[src*='googleusercontent']",
                    "div.section-image-container img",
                    "div.photos-album-container img",
                    "img.qaFoQ"
                ]
                
                for selector in image_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            try:
                                if element.is_displayed():
                                    url = element.get_attribute("src")
                                    if url and "googleusercontent.com" in url:
                                        # Transform URL to get the highest resolution (w0-h0-k-no gets original image size with no restrictions)
                                        high_res_url = re.sub(r'=(w\d+-h\d+|w\d+|h\d+|s\d+)(.*)', '=w0-h0-k-no', url)
                                        if high_res_url not in image_urls and high_res_url not in skipped_urls:
                                            accepted = True
                                            if callback:
                                                accepted = callback(high_res_url)
                                            if accepted:
                                                image_urls.add(high_res_url)
                                                # Save to CSV if needed
                                                if csv_path:
                                                    self.save_url_to_csv(csv_path, high_res_url, url_index)
                                                    url_index += 1
                                            else:
                                                skipped_urls.add(high_res_url)
                            except StaleElementReferenceException:
                                continue
                    except Exception:
                        continue
            
            logger.info(f"Extracted {len(image_urls)} unique image URLs directly from page")
            
        except Exception as e:
            logger.error(f"Error during direct image extraction: {str(e)}")
            
        return list(image_urls)

    def download_image(self, url, location_name, index):
        """
        Download an image from a URL
        
        Args:
            url (str): URL of the image
            location_name (str): Name of the location for the filename
            index (int): Index of the image for the filename
            
        Returns:
            bool: True if download was successful, False otherwise
        """
        try:
            # Create location-specific directory
            location_dir = os.path.join(self.download_dir, self._sanitize_filename(location_name))
            if not os.path.exists(location_dir):
                os.makedirs(location_dir)
                
            # Extract file extension from URL or default to .jpg
            parsed_url = urlparse(url)
            path = unquote(parsed_url.path)
            ext = os.path.splitext(path)[1]
            if not ext or ext == '.':
                ext = '.jpg'
                
            # Create filename
            filename = f"{self._sanitize_filename(location_name)}_{index}{ext}"
            filepath = os.path.join(location_dir, filename)
            
            # Log download attempt
            logger.debug(f"Attempting to download: {url[:50]}... to {filepath}")
            
            # Download the image with timeout and headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.google.com/maps'
            }
            
            # Use requests with retry mechanism
            max_retries = 3
            for retry in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, timeout=30)
                    response.raise_for_status()
                    break
                except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                    if retry < max_retries - 1:
                        logger.warning(f"Retry {retry+1}/{max_retries} for image {index}: {str(e)}")
                        time.sleep(2)  # Wait before retry
                    else:
                        raise
            
            # If file exists, don't overwrite
            if os.path.exists(filepath):
                logger.info(f"File already exists, skipping: {filename}")
                return True
                
            # Save the image
            with open(filepath, 'wb') as f:
                f.write(response.content)
                
            # Check if file was created successfully
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"Successfully downloaded: {filename}")
                # Print first few and periodic updates
                if index <= 5 or index % 10 == 0:
                    print(f"Downloaded image #{index}: {filename}")
                return True
            else:
                logger.error(f"File was not created or is empty: {filepath}")
                return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading image {index}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading image {index}: {str(e)}")
            return False

    def download_all_images(self, image_urls, location_name, max_workers=5):
        """
        Download all images using multiple threads
        
        Args:
            image_urls (list): List of image URLs
            location_name (str): Name of the location
            max_workers (int): Maximum number of worker threads
            
        Returns:
            int: Number of successfully downloaded images
        """
        if not image_urls:
            logger.warning("No image URLs to download")
            return 0
            
        logger.info(f"Starting download of {len(image_urls)} images with {max_workers} workers")
        print(f"Starting download of {len(image_urls)} images with {max_workers} workers")
        
        successful_downloads = 0
        
        # Use ThreadPoolExecutor for parallel downloads
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, url in enumerate(image_urls):
                futures.append(executor.submit(self.download_image, url, location_name, i+1))
                
            # Collect results with progress updates
            for i, future in enumerate(futures):
                if future.result():
                    successful_downloads += 1
                
                # Print progress
                if (i+1) % 5 == 0 or i+1 == len(futures):
                    print(f"Downloaded {successful_downloads}/{i+1} images...")
                    
        logger.info(f"Successfully downloaded {successful_downloads} out of {len(image_urls)} images")
        print(f"Successfully downloaded {successful_downloads} out of {len(image_urls)} images")
        return successful_downloads

    def _sanitize_filename(self, filename):
        """
        Sanitize a string to be used as a filename
        
        Args:
            filename (str): String to sanitize
            
        Returns:
            str: Sanitized string
        """
        # Replace invalid characters with underscore
        sanitized = re.sub(r'[\\/*?:"<>|]', '_', filename)
        # Remove leading/trailing whitespace and periods
        sanitized = sanitized.strip('. ')
        # Replace multiple spaces with single underscore
        sanitized = re.sub(r'\s+', '_', sanitized)
        return sanitized

    def close(self):
        """Close the WebDriver"""
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully")
            except Exception as e:
                logger.error(f"Error closing WebDriver: {str(e)}")

    def scrape_location_images(self, location_name, max_images=None, max_workers=5):
        """
        Main method to scrape images for a location
        
        Args:
            location_name (str): Name of the location to search
            max_images (int, optional): Maximum number of images to extract
            max_workers (int): Maximum number of worker threads for downloading
            
        Returns:
            tuple: (success status, number of images downloaded)
        """
        try:
            # Search for the location
            if not self.search_location(location_name):
                logger.error(f"Failed to find location: {location_name}")
                return False, 0
                
            # Wait for the location page to load
            time.sleep(3)
            
            # Open photos section
            if not self.open_photos_section():
                logger.error(f"Failed to open photos section for: {location_name}")
                return False, 0
                
            # Extract image URLs
            image_urls = self.extract_image_urls(max_images, location_name)
            if not image_urls:
                logger.warning(f"No images found for: {location_name}")
                return True, 0
                
            # If in --only-csv mode, skip downloading
            if max_workers == 0:
                logger.info(f"Skipping download as --only-csv mode is enabled. Found {len(image_urls)} image URLs.")
                print(f"Found {len(image_urls)} image URLs for: {location_name}")
                print(f"URLs saved to CSV. Skipping download as --only-csv mode is enabled.")
                return True, len(image_urls)
                
            # Download images
            downloaded_count = self.download_all_images(image_urls, location_name, max_workers)
            
            return True, downloaded_count
            
        except Exception as e:
            logger.error(f"Error during scraping process: {str(e)}")
            return False, 0
        finally:
            # Close the browser
            self.close()
                
    def extract_urls_only(self, location_name, max_images=None, show_progress=False, callback=None, skip_images=0):
        """
        Extract image URLs for a location without downloading
        
        Args:
            location_name (str): Name of the location to search
            max_images (int, optional): Maximum number of images to extract
            show_progress (bool): Whether to show detailed progress logging
            callback (callable, optional): Callback function for each new image URL
            skip_images (int): Number of images to skip from start of gallery
            
        Returns:
            list: List of image URLs, empty list if failed
        """
        try:
            logger.info(f"Extracting URLs for: {location_name}")
            
            # Search for the location
            if not self.search_location(location_name):
                logger.warning(f"Failed to find location: {location_name}")
                return []
                
            # Wait for the location page to load
            time.sleep(1)
            
            # Open photos section
            if not self.open_photos_section():
                logger.warning(f"Failed to open photos section for: {location_name}")
                return []
                
            # Extract image URLs (without CSV saving)
            original_save_csv = self.save_csv
            self.save_csv = False  # Temporarily disable CSV
            
            image_urls = self.extract_image_urls(max_images, location_name, show_progress, callback=callback, skip_images=skip_images)
            
            self.save_csv = original_save_csv  # Restore original setting
            
            if image_urls:
                logger.info(f"Found {len(image_urls)} images for {location_name}")
            else:
                logger.warning(f"No images found for {location_name}")
                
            return image_urls
            
        except Exception as e:
            logger.error(f"Error extracting URLs for {location_name}: {str(e)}")
            return []

    def fast_extract_urls(self, location_name, max_images=20, callback=None):
        """
        Fast URL extraction using photo-grid scrolling + bulk JS extraction.
        ~5-10x faster than extract_urls_only — no per-image "Next" clicking.

        Strategy:
          1. Search → place page  (smart WebDriverWait instead of fixed sleeps)
          2. Click Photos tab     (lands on the thumbnail grid, not the gallery)
          3. Scroll the grid      (loads more images into the DOM)
          4. One JS call          (grabs ALL googleusercontent URLs at once)
          5. Transform + return   (converts to high-res w0-h0-k-no format)

        Falls back to the original extract_urls_only on any failure.
        """
        image_urls = set()

        try:
            logger.info(f"[FAST] Starting fast extraction for: {location_name}")

            # ── 1. Navigate to Google Maps and search ────────────────────────
            self.driver.get("https://www.google.com/maps")

            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input#searchboxinput, input[name='q']")
                )
            )
            search_box.clear()
            search_box.send_keys(location_name)
            search_box.send_keys(Keys.ENTER)

            # Smart wait: look for place-page heading OR search result cards
            time.sleep(1.5)  # minimal buffer for Maps routing

            # ── 2. Land on the place page ────────────────────────────────────
            try:
                WebDriverWait(self.driver, 4).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "h1.DUwDvf, div.fontHeadlineLarge")
                    )
                )
                logger.info("[FAST] Direct place page loaded")
            except TimeoutException:
                # Search results page — click first result
                logger.info("[FAST] Search results page, clicking first result")
                try:
                    result = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, "div.Nv2PK, a.hfpxzc, div[jsaction*='placecard']")
                        )
                    )
                    result.click()
                    WebDriverWait(self.driver, 6).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "h1.DUwDvf, div.fontHeadlineLarge")
                        )
                    )
                except TimeoutException:
                    logger.warning("[FAST] Could not confirm place page, continuing anyway")

            # ── 3. Click the Photos tab ───────────────────────────────────────
            photos_clicked = False
            photo_tab_selectors = [
                "button[aria-label*='photo' i]",
                "button[data-item-id*='photo' i]",
                "a[aria-label*='photo' i]",
                "button[jsaction*='photo']",
                "button[aria-label*='Photos']",
            ]

            for selector in photo_tab_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.is_displayed():
                            self.driver.execute_script("arguments[0].click();", el)
                            photos_clicked = True
                            logger.info(f"[FAST] Clicked Photos tab: {selector}")
                            break
                    if photos_clicked:
                        break
                except Exception:
                    continue

            if not photos_clicked:
                try:
                    btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH,
                            "//button[.//div[contains(translate(text(),'PHOTOS','photos'),'photos')]]"
                        ))
                    )
                    self.driver.execute_script("arguments[0].click();", btn)
                    photos_clicked = True
                    logger.info("[FAST] Clicked Photos tab via XPath")
                except Exception:
                    logger.warning("[FAST] Photos tab not found, extracting from current page")

            # Wait for photo grid to render (needs enough time for lazy images)
            time.sleep(2.5)

            # ── 4. Scroll the photo grid to load more images ─────────────────
            scroll_rounds = max(3, (max_images // 5) + 1)

            scroll_container = None
            for sel in ["div.m6QErb.DxyBCb", "div.m6QErb", "div[role='main']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    scroll_container = els[0]
                    break

            for _ in range(scroll_rounds):
                try:
                    if scroll_container:
                        self.driver.execute_script(
                            "arguments[0].scrollTop += 3000;", scroll_container
                        )
                    # Also scroll window — catches cases where container isn't found
                    self.driver.execute_script("window.scrollBy(0, 3000);")
                    time.sleep(0.8)  # allow lazy-loaded images to appear
                except Exception:
                    pass

            # ── 5. Comprehensive bulk URL extraction via JS ───────────────────
            # Google Maps uses several rendering strategies: img src, srcset,
            # data-src (lazy load), and background-image CSS. Capture all of them.
            all_raw = self.driver.execute_script("""
                const urls = new Set();
                const isGoog = u => u && (u.includes('googleusercontent') || u.includes('lh3.google') || u.includes('lh5.google') || u.includes('lh6.google'));

                // <img> — src, srcset, data-src, data-original
                document.querySelectorAll('img').forEach(img => {
                    if (isGoog(img.src)) urls.add(img.src);
                    if (isGoog(img.dataset.src)) urls.add(img.dataset.src);
                    if (isGoog(img.dataset.original)) urls.add(img.dataset.original);
                    if (img.srcset) {
                        img.srcset.split(',').forEach(s => {
                            const u = s.trim().split(' ')[0];
                            if (isGoog(u)) urls.add(u);
                        });
                    }
                });

                // background-image in inline style
                document.querySelectorAll('[style*="background"]').forEach(el => {
                    const bg = el.style.backgroundImage || '';
                    const m = bg.match(/url\\(["']?(https?:[^"')]+)["']?\\)/);
                    if (m && isGoog(m[1])) urls.add(m[1]);
                });

                // data attributes with google URLs
                document.querySelectorAll('[data-src],[data-original],[data-bg]').forEach(el => {
                    ['data-src','data-original','data-bg'].forEach(attr => {
                        const v = el.getAttribute(attr);
                        if (isGoog(v)) urls.add(v);
                    });
                });

                return Array.from(urls);
            """) or []

            # Diagnostic: log current URL + total img count to aid debugging
            try:
                page_url = self.driver.current_url
                total_imgs = self.driver.execute_script(
                    "return document.querySelectorAll('img').length;"
                )
                logger.info(
                    f"[FAST] Page URL: {page_url[:80]}... | Total <img> tags: {total_imgs}"
                )
            except Exception:
                pass

            logger.info(f"[FAST] Raw URLs found: {len(all_raw)}")

            # ── 6. Deduplicate, convert to high-res, fire callback ────────────
            for url in all_raw:
                if not url or not any(d in url for d in ('googleusercontent', 'lh3.google', 'lh5.google', 'lh6.google')):
                    continue

                high_res = re.sub(
                    r'=(w\d+-h\d+|w\d+|h\d+|s\d+)(.*)', '=w0-h0-k-no', url
                )

                if high_res not in image_urls:
                    image_urls.add(high_res)
                    if callback:
                        callback(high_res)

                    if max_images and len(image_urls) >= max_images:
                        break


            logger.info(
                f"[FAST] Extracted {len(image_urls)} unique images for '{location_name}'"
            )

            # Fall back to the original method if we found nothing
            if not image_urls:
                logger.warning(
                    "[FAST] No images found via fast method — falling back to gallery extraction"
                )
                return self.extract_urls_only(location_name, max_images, callback=callback)

            return list(image_urls)

        except Exception as e:
            logger.error(f"[FAST] Fast extraction failed for '{location_name}': {e}")
            logger.info("[FAST] Falling back to standard gallery extraction...")
            return self.extract_urls_only(location_name, max_images, callback=callback)

    def process_locations_list(self, locations_list, max_images=None, show_progress=True):
        """
        Process a list of locations and extract image URLs
        
        Args:
            locations_list (list): List of location names (strings)
            max_images (int, optional): Maximum number of images per location
            show_progress (bool): Whether to show detailed progress logging
            
        Returns:
            list: Results in JSON format with location names and image URLs
        """
        results = []
        
        if not isinstance(locations_list, list):
            logger.error("Input must be a list of location names")
            return results
        
        total_locations = len(locations_list)
        print(f"Processing {total_locations} locations")
        print("-" * 50)
        
        for i, location_name in enumerate(locations_list, 1):
            if not isinstance(location_name, str):
                logger.warning(f"Invalid location type at index {i-1}: {type(location_name)}. Skipping.")
                continue
                
            location_name = location_name.strip()
            if not location_name:
                logger.warning(f"Empty location name at index {i-1}. Skipping.")
                continue
                
            print(f"\n[{i}/{total_locations}] Processing: {location_name}")
            logger.info(f"Processing location {i}/{total_locations}: {location_name}")
            
            try:
                # Extract URLs for this location with progress tracking
                image_urls = self.extract_urls_only(location_name, max_images, show_progress)
                
                location_result = {
                    "location_name": location_name,
                    "image_urls": image_urls,
                    "images_found": len(image_urls)
                }
                results.append(location_result)
                
                print(f"Completed: {len(image_urls)} images found for '{location_name}'")
                
                # Small delay between locations to avoid being blocked
                if i < total_locations:  # Don't delay after the last location
                    print(f"Waiting 3 seconds before next location...")
                    time.sleep(3)
                
            except Exception as e:
                logger.error(f"Error processing {location_name}: {str(e)}")
                # Add entry with empty results for failed locations
                location_result = {
                    "location_name": location_name,
                    "image_urls": [],
                    "images_found": 0,
                    "error": str(e)
                }
                results.append(location_result)
                print(f"Error processing '{location_name}': {str(e)}")
        
        return results

    def save_results_to_json(self, results, output_file):
        """
        Save results to a JSON file
        
        Args:
            results (list): Results data to save
            output_file (str): Path to output JSON file
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results saved to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving results to JSON: {str(e)}")
            return False

    def batch_extract_urls_from_list(self, locations_list, output_file=None, max_images=None, show_progress=True):
        """
        Main method for batch processing a list of locations
        
        Args:
            locations_list (list): List of location names (strings)
            output_file (str, optional): Path to output JSON file for results
            max_images (int, optional): Maximum images per location
            show_progress (bool): Whether to show detailed progress logging
            
        Returns:
            dict: Dictionary containing results and summary info
        """
        try:
            print(f"Starting batch URL extraction for {len(locations_list)} locations")
            if output_file:
                print(f"Output file: {output_file}")
            if max_images:
                print(f"Max images per location: {max_images}")
            else:
                print(f"Max images per location: No limit (all available)")
            print("-" * 70)
            
            # Process all locations
            results = self.process_locations_list(locations_list, max_images, show_progress)
            
            # Calculate summary statistics
            total_locations = len(results)
            successful_locations = len([r for r in results if r["images_found"] > 0])
            total_images = sum(r["images_found"] for r in results)
            failed_locations = len([r for r in results if "error" in r])
            
            summary = {
                "total_locations_processed": total_locations,
                "successful_locations": successful_locations,
                "failed_locations": failed_locations,
                "total_images_found": total_images,
                "average_images_per_location": round(total_images / max(successful_locations, 1), 2)
            }
            
            # Prepare final output
            output_data = {
                "summary": summary,
                "locations": results
            }
            
            # Save to file if specified
            if output_file:
                if self.save_results_to_json(output_data, output_file):
                    print(f"\nResults saved to: {output_file}")
                else:
                    print("\nFailed to save results to file")
            
            # Print summary
            print(f"\nFinal Summary:")
            print(f"  • Total locations processed: {total_locations}")
            print(f"  • Successful extractions: {successful_locations}")
            print(f"  • Failed extractions: {failed_locations}")
            print(f"  • Total images found: {total_images}")
            print(f"  • Average images per successful location: {summary['average_images_per_location']}")
            
            if failed_locations > 0:
                print(f"\nFailed locations:")
                for result in results:
                    if "error" in result:
                        print(f"    • {result['location_name']}: {result['error']}")
            
            return output_data
            
        except Exception as e:
            logger.error(f"Error during batch processing: {str(e)}")
            print(f"Batch processing failed: {str(e)}")
            return {"summary": {"total_locations_processed": 0, "successful_locations": 0, "failed_locations": 0, "total_images_found": 0}, "locations": []}
        finally:
            self.close()

def scrape_locations_list(locations_list, output_file=None, max_images=None, headless=True, timeout=30, show_progress=True):
    """
    Standalone function to scrape image URLs from a list of locations
    
    Args:
        locations_list (list): List of location names (strings)
        output_file (str, optional): Path to save JSON results
        max_images (int, optional): Maximum images per location
        headless (bool): Run browser in headless mode
        timeout (int): Timeout for WebDriver operations
        show_progress (bool): Whether to show detailed progress logging
        
    Returns:
        dict: Results with summary and location data
    """
    scraper = None
    try:
        # Initialize scraper
        scraper = GoogleMapsImageScraper(
            headless=headless,
            timeout=timeout,
            save_csv=False  # Don't save CSV for batch processing
        )
        
        # Process the list
        return scraper.batch_extract_urls_from_list(locations_list, output_file, max_images, show_progress)
        
    except Exception as e:
        logger.error(f"Error in scrape_locations_list: {str(e)}")
        return {"summary": {"total_locations_processed": 0, "successful_locations": 0, "failed_locations": 0, "total_images_found": 0}, "locations": []}
    finally:
        if scraper:
            scraper.close()
                
def main():
    """Main function to run the scraper from command line"""
    parser = argparse.ArgumentParser(description='Google Maps Image Scraper')
    parser.add_argument('location', type=str, nargs='?', help='Location name to search for (for single location mode)')
    parser.add_argument('--list-input', type=str, help='Comma-separated list of locations for batch processing')
    parser.add_argument('--output-json', type=str, help='Output JSON file for results (for batch mode)')
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    parser.add_argument('--download-dir', type=str, default='downloaded_images', help='Directory to save downloaded images')
    parser.add_argument('--max-images', type=int, default=None, help='Maximum number of images to download/extract')
    parser.add_argument('--max-workers', type=int, default=5, help='Maximum number of worker threads for downloading')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds for WebDriverWait')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with more detailed logs')
    parser.add_argument('--no-headless', action='store_true', help='Force browser to run in visible mode (overrides --headless)')
    parser.add_argument('--retry-attempts', type=int, default=3, help='Number of retry attempts for each step')
    parser.add_argument('--no-csv', action='store_true', help='Disable saving URLs to CSV file')
    parser.add_argument('--only-csv', action='store_true', help='Only save URLs to CSV, don\'t download images')
    parser.add_argument('--urls-only', action='store_true', help='Only extract URLs to JSON, don\'t download images')
    
    args = parser.parse_args()
    
    # Configure logging level based on debug flag
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.info("Debug mode enabled")
    
    # Determine headless mode
    use_headless = args.headless and not args.no_headless
    
    # Check for list input mode
    if args.list_input:
        # Parse the comma-separated list
        locations_list = [loc.strip() for loc in args.list_input.split(',') if loc.strip()]
        
        if not locations_list:
            print("No valid locations found in list input")
            return 1
            
        print(f"Batch mode: Processing {len(locations_list)} locations")
        
        # Use the standalone function
        results = scrape_locations_list(
            locations_list,
            args.output_json,
            args.max_images,
            use_headless,
            args.timeout
        )
        
        return 0 if results["summary"]["total_locations_processed"] > 0 else 1
    
    elif not args.location:
        print("Either provide a location name or use --list-input for batch processing")
        print("Example: python script.py --list-input 'Eiffel Tower,Big Ben,Statue of Liberty' --output-json results.json")
        return 1
    
    # Single location mode (existing functionality)
    try:
        print(f"Initializing scraper for: {args.location}")
        print(f"Browser mode: {'Headless' if use_headless else 'Visible'}")
        print(f"CSV mode: {'Disabled' if args.no_csv else 'Enabled'}")
        
        # Initialize scraper
        scraper = GoogleMapsImageScraper(
            headless=use_headless,
            download_dir=args.download_dir,
            timeout=args.timeout,
            save_csv=not args.no_csv
        )
        
        # Run scraper with retry logic
        success = False
        downloaded_count = 0
        attempts = 0
        
        while not success and attempts < args.retry_attempts:
            if attempts > 0:
                print(f"Retry attempt {attempts}/{args.retry_attempts}...")
                
            if args.urls_only:
                # Only extract URLs
                image_urls = scraper.extract_urls_only(args.location, args.max_images)
                if image_urls:
                    # Save to JSON format
                    results = {
                        "summary": {"total_locations_processed": 1, "successful_locations": 1, "total_images_found": len(image_urls)},
                        "locations": [{
                            "location_name": args.location,
                            "image_urls": image_urls,
                            "images_found": len(image_urls)
                        }]
                    }
                    output_file = args.output_json or f"{scraper._sanitize_filename(args.location)}_urls.json"
                    if scraper.save_results_to_json(results, output_file):
                        print(f"Extracted {len(image_urls)} URLs and saved to: {output_file}")
                        success = True
                    else:
                        print("Failed to save URLs to JSON")
                else:
                    print("No URLs found")
            else:
                # Original functionality with downloading
                success, downloaded_count = scraper.scrape_location_images(
                    args.location,
                    max_images=args.max_images,
                    max_workers=0 if args.only_csv else args.max_workers
                )
            
            if success and (downloaded_count > 0 or args.only_csv or args.urls_only):
                break
                
            attempts += 1
            if attempts < args.retry_attempts and not success:
                print("Retrying in 3 seconds...")
                time.sleep(3)
                
                # Reinitialize scraper for next attempt
                scraper = GoogleMapsImageScraper(
                    headless=use_headless,
                    download_dir=args.download_dir,
                    timeout=args.timeout,
                    save_csv=not args.no_csv
                )
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
        return 1
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        logger.exception("Unhandled exception in main")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)