import os
import time
import logging
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pickle
from dotenv import load_dotenv
import hashlib
import json
from typing import List, Tuple, Optional
import requests
from requests.exceptions import RequestException
import tempfile
import shutil
from pathlib import Path
import secrets
import string
from selenium.webdriver.support.ui import Select

# Configure logging with secure file permissions
log_file = Path('bin_calendar.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
log_file.chmod(0o600)  # Set secure permissions

# Load environment variables
load_dotenv()

# Constants
SCOPES = ['https://www.googleapis.com/auth/calendar']
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
TOKEN_FILE = 'token.pickle'
CREDENTIALS_FILE = 'calendarcredentials.json'
WEBSITE_URL = 'https://www.thehills.nsw.gov.au/Residents/Waste-Recycling/When-is-my-bin-day/Check-which-bin-to-put-out'
MAX_ADDRESS_LENGTH = 200
MIN_ADDRESS_LENGTH = 5

def generate_secure_temp_dir() -> Path:
    """Create a secure temporary directory."""
    temp_dir = Path(tempfile.mkdtemp())
    temp_dir.chmod(0o700)  # Set secure permissions
    return temp_dir

def validate_address(address: str) -> bool:
    """Validate the address format to ensure suburb, street, and house number are present."""
    if not isinstance(address, str):
        logger.error("Address must be a string")
        return False

    address = address.strip()
    # Expecting format: "house_number, street, suburb"
    parts = [part.strip() for part in address.split(',')]
    if len(parts) != 3:
        logger.error("Address must be in the format: 'house_number, street, suburb'")
        return False

    house, street, suburb = parts
    if not house or not street or not suburb:
        logger.error("House number, street, and suburb must all be provided")
        return False

    # You can add more specific validation for each part if needed
    return True

def get_google_calendar_service() -> Optional[build]:
    """Get Google Calendar service with improved security."""
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                logger.error(f"Error loading token file: {e}")
                return None
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refreshing token: {e}")
                    return None
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    logger.error("Credentials file not found")
                    return None
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error in OAuth flow: {e}")
                    return None
            
            # Save token with secure permissions
            try:
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)
                Path(TOKEN_FILE).chmod(0o600)
            except Exception as e:
                logger.error(f"Error saving token: {e}")
                return None
        
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Error setting up Google Calendar service: {str(e)}")
        return None

def add_to_calendar(service: build, bin_type: str, collection_date: datetime) -> bool:
    """Add event to calendar with enhanced security. Event is set a day before collection."""
    try:
        # Validate inputs
        if not isinstance(bin_type, str) or not bin_type.strip():
            logger.error("Invalid bin type")
            return False
            
        if not isinstance(collection_date, datetime):
            logger.error("Invalid collection date")
            return False
            
        # Sanitize bin type
        bin_type = bin_type.strip()
        if len(bin_type) > 100:  # Reasonable maximum length
            logger.error("Bin type too long")
            return False

        # Set event date to one day before collection
        reminder_date = collection_date - timedelta(days=1)

        event = {
            'summary': f'{bin_type} Bin Collection Tomorrow',
            'description': f'Reminder: {bin_type} bin will be collected on {collection_date.strftime("%A, %d %B %Y")}',
            'start': {
                'date': reminder_date.strftime('%Y-%m-%d'),
                'timeZone': 'Australia/Sydney',
            },
            'end': {
                'date': reminder_date.strftime('%Y-%m-%d'),
                'timeZone': 'Australia/Sydney',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 24 * 60},
                ],
            },
        }

        service.events().insert(calendarId='primary', body=event).execute()
        return True
    except HttpError as e:
        logger.error(f"Error adding event to calendar: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error adding event to calendar: {str(e)}")
        return False

def get_bin_schedule(address: str) -> List[Tuple[str, datetime]]:
    """Get bin schedule with enhanced security."""
    if not validate_address(address):
        logger.error("Invalid address format")
        return []

    # Read dropdown values from environment
    suburb_value = os.getenv('SUBURB', '').strip()
    street_value = os.getenv('STREET', '').strip()
    house_value = os.getenv('HOUSE_NUMBER', '').strip()
    if not suburb_value or not street_value or not house_value:
        logger.error("Missing SUBURB, STREET, or HOUSE_NUMBER in .env file")
        return []

    temp_dir = generate_secure_temp_dir()
    chrome_options = Options()
    #chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
    chrome_options.add_argument(f'--user-data-dir={temp_dir}')
    
    driver = None
    try:
        chrome_path = ChromeDriverManager().install()
        if "THIRD_PARTY_NOTICES.chromedriver" in chrome_path:
            chrome_path = chrome_path.replace("THIRD_PARTY_NOTICES.chromedriver", "chromedriver")
        driver = webdriver.Chrome(
            service=Service(chrome_path),
            options=chrome_options
        )
        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        
        # Navigate to the website
        driver.get(WEBSITE_URL)
        
        # --- NEW DROPDOWN LOGIC ---
        # Suburb
        suburb_xpath = '/html/body/form/div[5]/div/div/div/div[1]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div[1]/div[2]/select'
        suburb_dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, suburb_xpath))
        )
        Select(suburb_dropdown).select_by_visible_text(suburb_value)

        # Street
        street_xpath = '/html/body/form/div[5]/div/div/div/div[1]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div[2]/div[2]/select'
        street_dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, street_xpath))
        )
        Select(street_dropdown).select_by_visible_text(street_value)

        # House Number
        house_xpath = '/html/body/form/div[5]/div/div/div/div[1]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div[3]/div[2]/select'
        house_dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, house_xpath))
        )
        Select(house_dropdown).select_by_visible_text(house_value)
        # --- END NEW DROPDOWN LOGIC ---

        # Wait for results to load
        time.sleep(2)
        
        # Get the bin schedule
        schedule = []
        # bin_elements = WebDriverWait(driver, REQUEST_TIMEOUT).until(
        #    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.bin-schedule-item'))
        # )
        
        # Wait for at least one bin type to appear
        bin_types = WebDriverWait(driver, REQUEST_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'h4.ng-binding'))
        )
        
        for bin_type_elem in bin_types:
            try:
                bin_type = bin_type_elem.text.strip()
                # The date is in the next sibling <p> element
                date_elem = bin_type_elem.find_element(By.XPATH, 'following-sibling::p[1]')
                date_text = date_elem.text.strip()
                # Extract the date string using regex
                match = re.search(r'Next collected on (.+)', date_text)
                if not match:
                    logger.error(f"Could not parse date from text: {date_text}")
                    continue
                date_str = match.group(1).strip()
                # Parse the date (e.g., 'Thursday, 5 June 2025')
                try:
                    collection_date = datetime.strptime(date_str, '%A, %d %B %Y')
                except ValueError:
                    logger.error(f"Invalid date format: {date_str}")
                    continue
                if collection_date.date() >= datetime.now().date():
                    schedule.append((bin_type, collection_date))
            except Exception as e:
                logger.error(f"Error processing bin element: {str(e)}")
                continue
        
        return schedule
    
    except TimeoutException:
        logger.error("Timeout while loading the website")
        return []
    except WebDriverException as e:
        logger.error(f"WebDriver error: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return []
    finally:
        if driver:
            driver.quit()
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {e}")

def main():
    """Main function with enhanced security."""
    try:
        # Get address from environment variable (optional, for validation/logging)
        address = os.getenv('ADDRESS', '').strip()
        if not address:
            logger.error("ADDRESS not set in environment or .env file")
            return

        # Get bin schedule (dropdown values are read from env)
        logger.info("Getting bin schedule for configured dropdown values...")
        schedule = get_bin_schedule(address)
        
        if not schedule:
            logger.error("No bin schedule found for the given address")
            return

        # Set up Google Calendar service
        logger.info("Setting up Google Calendar...")
        service = get_google_calendar_service()
        if not service:
            logger.error("Failed to set up Google Calendar service")
            return

        # Add events to calendar
        logger.info("Adding events to calendar...")
        success_count = 0
        for bin_type, collection_date in schedule:
            if add_to_calendar(service, bin_type, collection_date):
                success_count += 1
                logger.info(f"Added {bin_type} collection for {collection_date.strftime('%Y-%m-%d')}")

        logger.info(f"Successfully added {success_count} out of {len(schedule)} events to calendar")

    except Exception as e:
        logger.error(f"Unexpected error in main function: {str(e)}")

if __name__ == '__main__':
    main()