import datetime as dt
from functools import cache
import src.utils.settings as settings


@cache
def get_month_range() -> tuple:
    today = dt.datetime.now()
    next_month = today.replace(day=28) + dt.timedelta(days=4)

    month_start = today.replace(day=1)
    month_end = next_month - dt.timedelta(days=next_month.day)

    return month_start, month_end


@cache
def get_month_range_yesterday() -> tuple:
    today = dt.datetime.now() - dt.timedelta(days=1)
    next_month = today.replace(day=28) + dt.timedelta(days=4)

    month_start = today.replace(day=1)
    month_end = next_month - dt.timedelta(days=next_month.day)

    return month_start, month_end

@cache
def get_dates_range() -> tuple:
    today = dt.datetime.today()
    
    days_before = int(settings.get('days_before',30))
    days_after = int(settings.get('days_after',30))
    
    if days_before > 90: days_before = 90 # it's our default max value
    if days_after > 90: days_after = 90 # it's our default max value
    
    start_date = today-dt.timedelta(days=days_before)
    end_date = today+dt.timedelta(days=days_after)
    
    return start_date, end_date
    
    
    
