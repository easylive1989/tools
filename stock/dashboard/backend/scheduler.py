import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.margin import fetch_margin
from fetchers.ndc import fetch_ndc
from fetchers.news import fetch_news
from db import purge_old_data

TST = pytz.timezone("Asia/Taipei")

def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TST)

    # Every 15 minutes — yfinance returns stale data outside market hours so
    # over-fetching is harmless and simplifies the schedule
    scheduler.add_job(fetch_taiex,      "interval", minutes=15, id="taiex",  replace_existing=True)
    scheduler.add_job(fetch_fx,         "interval", minutes=15, id="fx",     replace_existing=True)
    scheduler.add_job(fetch_all_stocks, "interval", minutes=15, id="stocks", replace_existing=True)

    # Daily 08:00 TST
    scheduler.add_job(fetch_fear_greed, CronTrigger(hour=8,  minute=0, timezone=TST), id="fear_greed", replace_existing=True)

    # Daily 18:00 TST (after TWSE settlement)
    scheduler.add_job(fetch_margin,     CronTrigger(hour=18, minute=0, timezone=TST), id="margin",     replace_existing=True)

    # Monthly on the 1st at 09:00 TST
    scheduler.add_job(fetch_ndc,        CronTrigger(day=1,  hour=9,  minute=0, timezone=TST), id="ndc", replace_existing=True)

    # News: every 30 minutes
    scheduler.add_job(fetch_news, "interval", minutes=30, id="news", replace_existing=True)

    # Weekly cleanup of data older than 3 years
    scheduler.add_job(purge_old_data,   CronTrigger(day_of_week="sun", hour=0, timezone=TST), id="cleanup", replace_existing=True)

    scheduler.start()
    return scheduler
