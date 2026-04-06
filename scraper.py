import time
import logging
log = logging.getLogger(__name__)
from datetime import datetime
import re

import requests
from bs4 import BeautifulSoup
import pymongo

BASE_URL = "https://www.federalreserve.gov/monetarypolicy/fomcminutes{date}.htm"
scraper_sleep = 2
DATES_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
DATES_HISTORIC_URL = "https://federalreserve.gov/monetarypolicy/fomc_historical_year.htm"
DATES = [DATES_URL, DATES_HISTORIC_URL]
MONTH_TO_NUM = {"january": "01", "feburary": "02", "march": "03", "april": "04",\
                "may": "05", "june": "06", "july": "07", "august": "08",\
                "september": "09", "october": "10", "november": "11", "december": "12"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (academic research scraper; contact: your@email.com)"
    )
}

class DB_Manager():
    def __init__(self):
        self.client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
        self.db = self.client["fomc"]
        self.metadata = self.db["fomc_metadata"]
        self.minutes_raw = self.db["fomc_minutes_raw"]

    def scrape_date(self):
        resps = []
        for url in DATES:
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                resps.append(soup)

            except requests.RequestException as e:
                log.error(f"Request for date info failed for {url}: {e}")
                
        return resps

    def get_meeting_dates_from_calendar(self, url):
        count = self.metadata.count_documents({})
        print(f"Collection has {count} documents after update")

        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        meeting_dates = []

        for heading in soup.find_all("div", class_="panel-heading"):
            h4 = heading.find("h4")
            if not h4:
                continue
            match = re.match(r"(\d{4})\s+FOMC Meetings", h4.get_text(strip=True))
            if not match:
                continue
            current_year = int(match.group(1))

            # Iterate over each meeting row
            for meeting_row in heading.find_next_siblings("div", class_="fomc-meeting"):
                month_div = meeting_row.find("div", class_=lambda c: c and "fomc-meeting__month" in c)

                date_div = meeting_row.find("div", class_=lambda c: c and "fomc-meeting__date" in c)
            
                if not month_div or not date_div:
                    continue

                if "notation" in date_div.get_text(strip=True).lower():
                    continue

                month_text = month_div.find("strong").get_text(strip=True)

                # handle different month formats
                for i in ['/', '⁄', '∕']:
                    if i in month_text:
                        month_str = month_text[-3:]
                        break
                    else:
                        month_str = month_text

                try:
                    month_num = datetime.strptime(month_str, "%b").month
                except ValueError:
                    month_num = datetime.strptime(month_str, "%B").month

                raw_date = date_div.get_text(strip=True).replace("*", "").strip()

                if not raw_date or raw_date in ("TBD", "—"):
                    continue

                # Handle Date Logic
                if "-" in raw_date:
                    first_day, last_day = raw_date.split("-")
                    first_day, last_day = int(first_day), int(last_day)

                    # Month boundary e.g. "31-1" — ends in next month
                    if last_day < first_day:
                        next_month = month_num % 12 + 1
                        year = current_year + 1 if next_month == 1 else current_year
                        meeting_end = datetime(year, next_month, last_day)
                    else:
                        meeting_end = datetime(current_year, month_num, last_day)
                else:
                    meeting_end = datetime(current_year, month_num, int(raw_date))

                print(meeting_end)
                meeting_dates.append({
                    "meeting_date": meeting_end.strftime("%Y%m%d"),
                    "year": current_year,
                    "month": month_str,
                    "datetime": meeting_end,
                    "minutes_url": build_url(meeting_end.strftime("%Y%m%d")),
                    "scraped": False
                    })
        
        self.metadata.insert_many(meeting_dates)
        count = self.metadata.count_documents({})
        print(f"Collection has {count} documents after update")
            

    def scrape_minutes(self, url):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 404:
                log.warning(f"404 — not found: {url}")
                return None
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            log.error(f"Request failed for {url}: {e}")
            return None

def build_url(date_str:str):
    return BASE_URL.format(date=date_str)

db_manager = DB_Manager()
#db_manager.get_meeting_dates_from_calendar(DATES_URL)
db_manager.get_meeting_dates_from_calendar(DATES_HISTORIC_URL)

