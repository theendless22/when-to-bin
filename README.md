# ♻️ When-to-Bin: Automated Bin Collection Calendar Integration 🗑️

This script automates the process of checking your bin collection schedule from [The Hills Shire Council](https://www.thehills.nsw.gov.au/Residents/Waste-Recycling/When-is-my-bin-day/Check-which-bin-to-put-out) and adds reminders to your Google Calendar **one day before each collection**.

## ✨ Features

- 🤖 Uses Selenium to interact with the council website and select your address.
- 📅 Extracts upcoming bin collection dates for Rubbish, Garden Organics, and Recycling.
- ⏰ Adds Google Calendar events/reminders for each bin type, scheduled for the day before collection.
- 🔒 Secure handling of credentials and tokens.
- 📝 Logging of all actions and errors.

## 🛠️ Requirements

- 🐍 Python 3.8+
- 🌐 Google Chrome browser
- ⚙️ ChromeDriver (automatically managed)
- ☁️ Google Cloud project with Calendar API enabled and OAuth credentials (`calendarcredentials.json`)
- The following Python packages (install with `pip install -r requirements.txt`):
  - selenium
  - webdriver-manager
  - google-auth
  - google-auth-oauthlib
  - google-api-python-client
  - python-dotenv

## 🚀 Setup

1. **Clone this repository.**

2. **Create a `.env` file** in the project root with your address details:
    ```
    SUBURB=<ADD HERE>
    STREET=<ADD HERE>
    HOUSE_NUMBER=<ADD HERE>
    ADDRESS=<ADD HERE>
    ```

3. **Add your Google Calendar OAuth credentials**  
   Download your `calendarcredentials.json` from the Google Cloud Console and place it in the project root.

4. **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

5. **Run the script:**
    ```sh
    python bin_calendar.py
    ```
   - 🖥️ The first time you run it, a browser window will open for Google authentication. Approve access to your Google Calendar.
   - 🔑 The script will create a `token.pickle` file for future authentication.

## 📝 Notes

- 📆 **Events are created for the day before each bin collection.**
- 👤 Only the user(s) listed as test users in your Google Cloud OAuth consent screen can use the script unless the app is verified by Google.
- 🚫 `token.pickle` and `calendarcredentials.json` are ignored by Git for your security.
- 📄 Logs are written to `bin_calendar.log`.

## 🛟 Troubleshooting

- ⚠️ If you see errors about ChromeDriver, ensure it has executable permissions (`chmod +x path/to/chromedriver`).
- 🔒 If you see "Access blocked: ... has not completed the Google verification process", add your email as a test user in the Google Cloud Console.
- 🏷️ If the script cannot find your bin schedule, check that your `.env` values match the dropdown options on the council website.

---

**Maintained by:** Shruthi Naidu