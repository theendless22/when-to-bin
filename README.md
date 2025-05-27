# Bin Collection Calendar

A Python application that automatically adds your local council's bin collection schedule to your Google Calendar.

## Features

- Scrapes bin collection schedule from The Hills Shire Council website
- Validates and processes collection dates
- Automatically adds events to Google Calendar
- Sends email and popup reminders 24 hours before collection
- Secure handling of credentials and sensitive data

## Prerequisites

- Python 3.8 or higher
- Google Calendar API credentials
- Chrome browser installed
- The Hills Shire Council address

## Installation

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/bin-collection-calendar.git
cd bin-collection-calendar
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Add your address to the `.env` file

5. Set up Google Calendar API:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the Google Calendar API
   - Create OAuth 2.0 credentials
   - Download and save as `credentials.json` in the project root

## Usage

Run the script:
```bash
python bin_calendar.py
```

## Security

- All sensitive data is stored in environment variables
- Credentials are never committed to the repository
- Input validation and sanitization implemented
- Secure error handling and logging

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 