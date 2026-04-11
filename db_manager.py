import time
from datetime import datetime
import re
import logging
log = logging.getLogger(__name__)

import requests
from bs4 import BeautifulSoup
import pymongo

BASE_HISTORIC_URL = "https://www.federalreserve.gov/fomc/MINUTES/{year}/{date}min.htm"
BASE_URL = "https://www.federalreserve.gov/monetarypolicy/fomcminutes{date}.htm"
scraper_sleep = 5
DATES_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
DATES_HISTORIC_URL = "https://federalreserve.gov/monetarypolicy/fomc_historical_year.htm"

MONTH_TO_NUM = {"january": "01", "feburary": "02", "march": "03", "april": "04",\
                "may": "05", "june": "06", "july": "07", "august": "08",\
                "september": "09", "october": "10", "november": "11", "december": "12"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (academic research scraper; contact: chen.yuqi2@northeastern.edu)"
    )
}

def _parse_meeting_end(raw_date, current_year, month_num):
    """Return a datetime for the last day of a meeting, or None if the date is unusable."""
    if not raw_date or raw_date in ("TBD", "—"):
        return None
    if "-" in raw_date:
        first_day, last_day = raw_date.split("-")
        first_day, last_day = int(first_day), int(last_day)

        if last_day < first_day:
            next_month = month_num % 12 + 1
            year = current_year + 1 if next_month == 1 else current_year
            return datetime(year, next_month, last_day)
        else:
            return datetime(current_year, month_num, last_day)
    else:
        return datetime(current_year, month_num, int(raw_date))

def build_url(date_str: str):
    year = int(date_str[:4])
    if year <= 1995:
        return f"https://www.federalreserve.gov/fomc/MINUTES/{year}/{date_str}min.htm"
    elif year <= 2007:
        return f"https://www.federalreserve.gov/fomc/minutes/{date_str}.htm"
    else:
        return f"https://www.federalreserve.gov/monetarypolicy/fomcminutes{date_str}.htm"

def build_dates_url(year:int):
    if year < 2021:
        sub_url = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"
        return sub_url.format(year=year)
    else:
        return DATES_URL
    
def parse_month_date(month_text, date, current_year, date1 = None):
    day_range = []
    for sep in ['/', '⁄', '∕']:
        if sep in month_text:
            month_str = month_text[-3:]
        else:
            month_str = month_text

        try:
            month_num = datetime.strptime(month_str, "%b").month
        except ValueError:
            month_num = datetime.strptime(month_str, "%B").month

        
        if date1:
            raw_date = "-".join([date, date1])
        else:
            raw_date = date

        meeting_end = _parse_meeting_end(raw_date, current_year, month_num)
        date_str = meeting_end.strftime("%Y%m%d")
        day_range.append(date_str)

        if date1:
            meeting_end1 = _parse_meeting_end(raw_date, current_year, month_num)
            date_str1 = meeting_end1.strftime("%Y%m%d")
            day_range.append(date_str1)
        
        return day_range

class DB_Manager():
    def __init__(self):
        self.client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
        self.db = self.client["fomc"]
        self.metadata = self.db["fomc_metadata"]
        self.minutes_raw = self.db["fomc_minutes_raw"]
        self.minutes_clean = self.db["fomc_minutes_clean"]

        self.metadata.create_index([("meeting_date", pymongo.ASCENDING)], unique=True)
        self.minutes_raw.create_index([("meeting_date", pymongo.ASCENDING)], unique=True)
        self.minutes_raw.create_index([("raw_text", pymongo.TEXT)])

    def get_meeting_dates_from_calendar(self, start_year, end_year):

        unscraped_count = self.metadata.count_documents({"year": {"$gte": 1994, "$lte": 2020}})
        print(f"unscraped count: {unscraped_count}")
        meeting_dates = []
        # Handles different layout for historical data
        
            # Loop over historic years
        for current_year in range(start_year, end_year + 1):
            time.sleep(scraper_sleep)
            
            if current_year < 2011:
                
                sub_url = build_dates_url(current_year)
                resp = requests.get(sub_url, headers=HEADERS, timeout=15)
                print(f"URL: {sub_url}")
                print(f"Status: {resp.status_code}")
                soup = BeautifulSoup(resp.text, "html.parser")

                panels = soup.find_all("div", class_="panel-heading")
                for heading in panels:
                    print(f"Found {len(panels)} panel-heading divs")
                    h5 = heading.find("h5")
                    if not h5:
                        continue

                    match = re.search(r"(\w+)\s+(\d+)(?:-(\d+))?\s+Meeting.*(\d{4})", h5.get_text(strip=True))
                    if not match:
                        continue

                    month_str  = match.group(1)
                    first_day  = match.group(2)
                    last_day   = match.group(3)

                    try:
                        month_num = datetime.strptime(month_str, "%b").month
                    except ValueError:
                        month_num = datetime.strptime(month_str, "%B").month

                    meeting_end = _parse_meeting_end(first_day, current_year, month_num)
                    if last_day:
                        meeting_end2 = _parse_meeting_end(last_day, current_year, month_num)

                    if meeting_end is None:
                        print("meeting end is empty")
                        continue

                    date_str = meeting_end.strftime("%Y%m%d")
                    day_range = [date_str]
                    if last_day:
                        date_str2 = meeting_end2.strftime("%Y%m%d")
                        day_range.append(date_str2)

                    meeting_dates.append({
                        "meeting_date": day_range,
                        "year": current_year,
                        "month": month_str,
                        "datetime": meeting_end,
                        "minutes_url": build_url(date_str),
                        "scraped": False
                    })
                    unscraped_count -= 1
                    print(f"unscraped count: {unscraped_count}")

            elif current_year >= 2011 and current_year <= 2020:
        
                print(f"scraping {current_year}")
                url = build_dates_url(current_year)
                resp = requests.get(url, headers=HEADERS, timeout=15)

                print(f"URL: {url}")
                print(f"Status: {resp.status_code}")

                soup = BeautifulSoup(resp.text, "html.parser")

                panel_divs = soup.find_all("div", class_=lambda c: c and "panel-padded" in c)
                print(f"found {len(panel_divs)} panel divs")

                for p in panel_divs:
                    h5 = p.find("h5", class_="panel-heading--shaded")
                    

                    match = re.search(r"(\w+)\s+(\d+)(?:-(\d+))?\s+Meeting.*(\d{4})", h5.get_text(strip=True))
                    print(h5.get_text())

                    if not match:
                        continue

                    print(f"found h5 tag")
                    month_str  = match.group(1)
                    first_day  = match.group(2)
                    last_day   = match.group(3)

                    day_range = parse_month_date(month_text=month_str, date=first_day, \
                                                current_year=current_year, date1=last_day)
                    
                    meeting_dates.append({
                            "meeting_date": day_range,
                            "year": current_year,
                            "month": month_str,
                            "datetime": False,
                            "minutes_url": build_url(day_range[0]),
                            "scraped": False
                        })
                    unscraped_count -= 1
                    print(f"unscraped count: {unscraped_count}")
            else:
                # Different Logic for handling modern dates web layout
                url = build_dates_url(current_year)
                resp = requests.get(url, headers=HEADERS, timeout=15)

                print(f"URL: {sub_url}")
                print(f"Status: {resp.status_code}")

                soup = BeautifulSoup(resp.text, "html.parser")

                panels = soup.find_all("div", class_="panel-heading")
                for h in panels:
                    text = h.get_text(strip=True)

                for heading in panels:
                    print(f"Found {len(panels)} panel-heading divs")
                    h4 = heading.find("h4")
                    if not h4:
                        continue
                    match = re.match(r"(\d{4})\s+FOMC Meetings", h4.get_text(strip=True))
                    if not match:
                        continue
                    current_year = int(match.group(1))

                    for meeting_row in heading.find_next_siblings("div", class_="fomc-meeting"):
                        month_div = meeting_row.find("div", class_=lambda c: c and "fomc-meeting__month" in c)
                        date_div  = meeting_row.find("div", class_=lambda c: c and "fomc-meeting__date" in c)

                        if not month_div or not date_div:
                            continue
                        if "notation" in date_div.get_text(strip=True).lower():
                            continue

                        month_text = month_div.find("strong").get_text(strip=True)
                        raw_date   = date_div.get_text(strip=True).replace("*", "").strip()

                        if not raw_date or raw_date in ("TBD", "—"):
                            continue

                        # Handle split headings e.g. "Jan/Feb"
                        month_str = month_text
                        for sep in ['/', '⁄', '∕']:
                            if sep in month_text:
                                month_str = month_text[-3:]
                                break

                        try:
                            month_num = datetime.strptime(month_str, "%b").month
                        except ValueError:
                            month_num = datetime.strptime(month_str, "%B").month

                        meeting_end = _parse_meeting_end(raw_date, current_year, month_num)
                        if meeting_end is None:
                            continue

                        date_str = meeting_end.strftime("%Y%m%d")
                        meeting_dates.append({
                            "meeting_date": [date_str],
                            "year": current_year,
                            "month": month_str,
                            "datetime": meeting_end,
                            "minutes_url": build_url(date_str),
                            "scraped": False
                        })
                        unscraped_count -= 1
                        print(f"unscraped count: {unscraped_count}")

        if meeting_dates:
            self.metadata.insert_many(meeting_dates)
        count = self.metadata.count_documents({})
        print(f"Collection has {count} documents after update")
        

    def get_minute_docs(self):

        unscraped_count = self.metadata.count_documents({"scraped": False})
        print(f"unscraped count: {unscraped_count}")

        for doc in self.metadata.find({"scraped": False}):
            chair = None
            raw_text = None
            date_str = doc["meeting_date"]
            
            dates = date_str if isinstance(date_str, list) else [date_str]

            if any(self.minutes_raw.find_one({"date_str": d}) for d in dates):
                continue
            
            resp = None
            for d in dates:
                url = build_url(d)  # also use build_url_by_year not build_url
                
                for i in range(3):
                    try:
                        resp = requests.get(url, headers=HEADERS, timeout=15)
                        if resp.status_code == 200:
                            break
                    except requests.RequestException as e:
                        log.warning(f"Attempt {i+1} failed for {url}: {e}")
                        time.sleep(5)
                                    
            soup = BeautifulSoup(resp.text, "html.parser")

            attend_div = soup.find("div", class_="attendees")
            if attend_div:
                chair = attend_div.find("p").text


            # actual transcript starts after hr tag
                hr = soup.find("hr")
                if not hr:
                    log.warning(f"No hr tag found for {date_str}")
                    continue
                
                paragraphs = []
                for tag in hr.find_all_next("p"):
                    text = tag.get_text(strip=True)
                
                    if not text:
                        continue
                    if len(text) < 20:  
                        continue
                    if re.match(r"^\d+\.$", text):
                        continue
                        
                    paragraphs.append(text)
                raw_text = "\n\n".join(paragraphs)
            else:

                raw_text = " ".join(p.get_text(strip=True) for p in soup.find_all("p"))
                match = re.search(r"([\w\s]+),\s*Chair", raw_text)
                if match:
                    chair = match.group(1).strip()

            minute_doc = {"meeting_date": date_str, "year": date_str[:4],
                           "raw_text":raw_text,
                            "chair": chair, "scraped_at": datetime.now()}
            
            self.minutes_raw.insert_one(minute_doc)
            self.metadata.update_one(
                {"_id": doc["_id"]},
                {"$set": {"meeting_date": date_str,
                          "scraped": True, "scraped_at": datetime.now()}}
            )
            unscraped_count -= 1
            print(f"unscraped count: {unscraped_count}")

            time.sleep(scraper_sleep)

        

    def corpus_to_sentences(self):
        '''
        Return:
            a lists of lists of sentences
        '''
        for doc in self.minutes_raw.find():
            self._clean_doc(doc['raw_text'], 20)

    def _append_year(self):
        '''
        Helper function to update minutes_raw collection with year
        '''
        for doc in self.metadata.find():

            date_str = doc['meeting_date']

            print(date_str)

    def _clean_doc(self, raw_text:str, sent_len_filter:int):
        '''
        Return:
            a list of words
        '''
        sent_lst = [i for i in raw_text.split(". ") if len(i) > sent_len_filter]
        tokens = [i for i in" ".join(sent_lst).split(" ")]

    def get_minutes_stats(self):
        pipeline = [
            {"$group": {
                "_id": "$year",
                "avg_word_count": {
                    "$avg": {
                        "$size": {"$split": ["$raw_text", " "]}
                    }
                },
                "doc_count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]

        stats = list(self.minutes_raw.aggregate(pipeline))
        for s in stats:
            print(f"{s['_id']}: {s['doc_count']} docs, avg {s['avg_word_count']:.0f} words")

    def set_scrape(self, year):
        self.metadata.update_many(
            {"year": year},
            {"$set": {"scraped": False}}
            )

    def debug_html_structure(self, url):
        print(url)
        print()
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Print all top level divs and their classes
        for div in soup.find_all("div", recursive=False):
            print(div.get("class"), len(div.get_text(strip=True)))
        
        # Print first 500 chars of each p tag
        for i, p in enumerate(soup.find_all("p")):
            text = p.get_text(strip=True)
            if text:
                print(f"p[{i}]: {len(text)} chars — {text[:100]}")

    def get_dates_from_year(self, year):
        pipeline = [
        {"$match": {"year": year}},
        {"$project": {"meeting_date": 1, "_id": 0}},
        {"$limit": 1}
        ]

        return list(self.metadata.aggregate(pipeline))
    
    def get_keyword_count(self, *args):
        result = {}
        start = time.time()
        for keyword in args:
            pipeline = [
                {"$match": {"$text": {"$search": f'"{keyword}"'}}},
                {"$group": {"_id": None, "count": {"$sum": 1}}}
            ]
            docs = list(self.minutes_raw.aggregate(pipeline))
            result[keyword] = docs[0]["count"] if docs else 0

        fin = time.time()
        for k, v in result.items():
            print(f"{k} appeared in {v} docs\n")
        print(f"Text index query for {len(args)} terms took {(fin - start):4f} seconds\n")
        return result

db_manager = DB_Manager()
#db_manager.get_meeting_dates_from_calendar(2011,2020)
#db_manager.get_minute_docs()
#db_manager.get_minutes_stats()

db_manager.get_keyword_count("high inflation", "low inflation", \
                             "high unemployment", "low unemployment",\
                            )





#93-94 format: "https://www.federalreserve.gov/fomc/MINUTES/{year}/{date}min.htm"
#95-07 format: https://www.federalreserve.gov/fomc/minutes/{date}.htm
#08-26 format: https://www.federalreserve.gov/monetarypolicy/fomcminutes{date}.htm
