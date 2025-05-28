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
import yaml
import ansible.parsing.vault
from ansible.parsing.vault import VaultLib
from ansible.parsing.vault import VaultSecret
import getpass

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

def get_vault_password() -> str:
    """Get Ansible vault password from environment or prompt."""
    vault_password = os.getenv('ANSIBLE_VAULT_PASSWORD')
    if not vault_password:
        vault_password = getpass.getpass("Enter Ansible vault password: ")
    return vault_password

def get_credentials() -> dict:
    """Get credentials from Ansible vault."""
    try:
        vault_password = get_vault_password()
        vault = VaultLib([(VaultSecret(vault_password.encode()), None)])
        creds_path = Path('ansible/credentials.yml')
        
        if not creds_path.exists():
            raise FileNotFoundError("Ansible credentials file not found at ansible/credentials.yml")
        
        with open(creds_path, 'rb') as f:
            encrypted_data = f.read()
            decrypted_data = vault.decrypt(encrypted_data)
            creds = yaml.safe_load(decrypted_data)
            
            if not isinstance(creds, dict):
                raise ValueError("Invalid credentials format in vault file")
            
            return creds
            
    except Exception as e:
        logger.error(f"Error retrieving credentials: {e}")
        raise

# Get GitHub token from Ansible vault if not in environment
if not os.getenv('GITHUB_TOKEN'):
    try:
        creds = get_credentials()
        github_token = creds.get('github_pat')
        if github_token:
            os.environ['GITHUB_TOKEN'] = github_token
            logger.info("Successfully retrieved GitHub token from Ansible vault")
        else:
            logger.warning("GitHub token not found in Ansible vault")
    except Exception as e:
        logger.error(f"Failed to retrieve GitHub token: {e}")

# Constants
SCOPES = ['https://www.googleapis.com/auth/calendar']
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
TOKEN_FILE = 'token.pickle'
CREDENTIALS_FILE = 'credentials.json'
WEBSITE_URL = 'https://www.thehills.nsw.gov.au/Residents/Waste-Recycling/When-is-my-bin-day/Check-which-bin-to-put-out'
MAX_ADDRESS_LENGTH = 200
MIN_ADDRESS_LENGTH = 5

def generate_secure_temp_dir() -> Path:
    """Create a secure temporary directory."""
    temp_dir = Path(tempfile.mkdtemp())
    temp_dir.chmod(0o700)  # Set secure permissions
    return temp_dir

def validate_address(address: str) -> bool:
    """Validate the address format with enhanced security."""
    if not isinstance(address, str):
        logger.error("Address must be a string")
        return False
        
    address = address.strip()
    if not address or len(address) < MIN_ADDRESS_LENGTH or len(address) > MAX_ADDRESS_LENGTH:
        logger.error(f"Address length must be between {MIN_ADDRESS_LENGTH} and {MAX_ADDRESS_LENGTH} characters")
        return False
        
    # Enhanced validation pattern
    pattern = r'^[a-zA-Z0-9\s,.-]+$'
    if not re.match(pattern, address):
        logger.error("Address contains invalid characters")
        return False
        
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
    """Add event to calendar with enhanced security."""
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
    """Get bin schedule with enhanced security."""
    if not validate_address(address):
        logger.error("Invalid address format")
        return []

    temp_dir = generate_secure_temp_dir()
    chrome_options = Options()
    chrome_options.add_argument('--headless')
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
                
                # Validate date format
                try:
                    collection_date = datetime.strptime(date_text, '%d/%m/%Y')
                except ValueError:
                    logger.error(f"Invalid date format: {date_text}")
                    continue
                
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
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {e}")

def main():
    """Main function with enhanced security."""
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