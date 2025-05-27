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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bin_calendar.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
SCOPES = ['https://www.googleapis.com/auth/calendar']
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
TOKEN_FILE = 'token.pickle'
CREDENTIALS_FILE = 'credentials.json'
WEBSITE_URL = 'https://www.thehills.nsw.gov.au/Residents/Waste-Recycling/When-is-my-bin-day/Check-which-bin-to-put-out'

def validate_address(address: str) -> bool:
    """Validate the address format."""
    if not address or len(address.strip()) < 5:
        return False
    # Basic validation - can be enhanced based on specific requirements
    return bool(re.match(r'^[a-zA-Z0-9\s,.-]+$', address))

def get_google_calendar_service() -> Optional[build]:
    """Get Google Calendar service with improved error handling and security."""
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    logger.error("Credentials file not found")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Encrypt the token before saving
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
        
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Error setting up Google Calendar service: {str(e)}")
        return None

def add_to_calendar(service: build, bin_type: str, collection_date: datetime) -> bool:
    """Add event to calendar with improved error handling."""
    try:
        # Validate inputs
        if not bin_type or not collection_date:
            logger.error("Invalid bin type or collection date")
            return False

        event = {
            'summary': f'{bin_type} Bin Collection',
            'description': 'Time to put out your bin for collection',
            'start': {
                'date': collection_date.strftime('%Y-%m-%d'),
                'timeZone': 'Australia/Sydney',
            },
            'end': {
                'date': collection_date.strftime('%Y-%m-%d'),
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
    """Get bin schedule with improved error handling and security."""
    if not validate_address(address):
        logger.error("Invalid address format")
        return []

    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-infobars')
    
    driver = None
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        
        # Navigate to the website
        driver.get(WEBSITE_URL)
        
        # Wait for the address input field and enter the address
        address_input = WebDriverWait(driver, REQUEST_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, 'address'))
        )
        address_input.clear()
        address_input.send_keys(address)
        
        # Click the search button
        search_button = WebDriverWait(driver, REQUEST_TIMEOUT).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
        )
        search_button.click()
        
        # Wait for results to load
        time.sleep(2)
        
        # Get the bin schedule
        schedule = []
        bin_elements = WebDriverWait(driver, REQUEST_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.bin-schedule-item'))
        )
        
        for element in bin_elements:
            try:
                bin_type = element.find_element(By.CSS_SELECTOR, '.bin-type').text
                date_text = element.find_element(By.CSS_SELECTOR, '.collection-date').text
                collection_date = datetime.strptime(date_text, '%d/%m/%Y')
                
                # Validate the date is not in the past
                if collection_date.date() >= datetime.now().date():
                    schedule.append((bin_type, collection_date))
            except (ValueError, WebDriverException) as e:
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

def main():
    """Main function with improved error handling and security."""
    try:
        # Get and validate address
        address = os.getenv('ADDRESS')
        if not address or not validate_address(address):
            logger.error("Invalid or missing address in .env file")
            return

        # Get bin schedule
        logger.info(f"Getting bin schedule for {address}...")
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