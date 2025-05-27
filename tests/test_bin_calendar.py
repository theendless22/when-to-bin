import pytest
from datetime import datetime
from bin_calendar import validate_address, add_to_calendar

def test_validate_address():
    # Test valid addresses
    assert validate_address("123 Example Street, Suburb NSW 2000")
    assert validate_address("45 Main Road, Sydney NSW 2000")
    
    # Test invalid addresses
    assert not validate_address("")  # Empty address
    assert not validate_address("123")  # Too short
    assert not validate_address("123 Example St!")  # Invalid characters

def test_add_to_calendar():
    # Mock Google Calendar service
    class MockService:
        def events(self):
            return self
        
        def insert(self, calendarId, body):
            return self
        
        def execute(self):
            return True
    
    service = MockService()
    bin_type = "General Waste"
    collection_date = datetime.now()
    
    # Test successful calendar addition
    assert add_to_calendar(service, bin_type, collection_date)
    
    # Test invalid inputs
    assert not add_to_calendar(service, "", collection_date)  # Empty bin type
    assert not add_to_calendar(service, bin_type, None)  # None date 