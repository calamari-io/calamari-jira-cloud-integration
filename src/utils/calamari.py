import datetime as dt
from collections import defaultdict

import requests
from requests.auth import HTTPBasicAuth

import src.utils.settings as settings
from src.utils.date import get_dates_range

import logging

def api_call(path: str, body: dict|None = None, no_response: bool = False) -> dict|None:
    """ Make a call to Calamari API """

    url = f"{settings.get('calamari_api_url')}/api/{path}"
    auth = HTTPBasicAuth("calamari", settings.get("calamari_api_token"))
    headers={"Accept": "application/json"}

    res = requests.request(
        "POST", url,
        headers=headers,
        auth=auth,
        json=body,
    )
    logging.debug("Calamari API response [%s]: %s", res.status_code, res.text)
    logging.debug("Calamari API payload: %s", body)
    logging.debug("Calamari API headers: %s", headers)

    res.raise_for_status()
    return res.json() if not no_response else None


def get_employees() -> list:
    """ Return a list of employees from Calamari """

    results = []
    page = 0
    while True:
        res = api_call("employees/v1/list", body={"page": page})
        results.extend(res["employees"])

        if res["currentPage"] == res["totalPages"]:
            return results

        page = res["currentPage"] + 1

def get_employee(email: str) -> dict:
    """ Return employee configuration """
    
    return api_call("employees/v1/search", body={"employee": email})
    
def get_workweeks() -> list:
    """ Get workweeks configuration """
    
    return api_call("working-week/v1/all")
    
def get_workweek(workweeks: list, workweek_id: int) -> list|None:
    for workweek in workweeks:
        if workweek['id'] == workweek_id:
            return workweek
    return None
    

def get_working_hours(workweek: list, day: str) -> float|None:
    """ Find employee workweek configuration """
    
    for workday in workweek['workingDays']:
        if workday['dayName'] == day:
            if workday['duration']:
                return float(workday['duration']/60/60)
            else:
                return 0.0
    return None

def average_working_hours_per_week(workweek: list) -> float|None:
    sum=0.0
    days=0
    for workday in workweek['workingDays']:
        if workday['duration']:
           sum+=workday['duration']
           days+=1
    if sum == 0.0 or days == 0:
        return None
    return sum/days/60/60
    

def fetch_timesheets(email: str, date_from: str, date_to: str) -> list:
    """ Fetch employee timesheets from Calamari """

    return api_call("clockin/timesheetentries/v1/find", {"from": date_from, "to": date_to, "employees": [email]})


def sum_timesheets(worklogs: list) -> dict:
    """ Helper function to sum seconds worked per day """

    result = defaultdict(lambda: 0.0)
    for worklog in worklogs:
        result[worklog["started"][0:10]] += worklog["duration"]

    return result


def delete_timesheet(timesheet_id: int):
    """ Delete timesheet from Calamari """
    return api_call("clockin/timesheetentries/v1/delete", {"id": timesheet_id}, no_response=True)


def create_timesheet(person: str, shift_day: str, hours: float):
    """ Create timesheet entry in Calamari """

    shift_start = dt.datetime.fromisoformat(shift_day).replace(tzinfo=None).replace(hour=8)
    shift_end = shift_start + dt.timedelta(hours=hours)

    body = {
        "person": person,
        "shiftStart": shift_start.isoformat(timespec='seconds'),
        "shiftEnd": shift_end.isoformat(timespec='seconds'),
    }
    api_call("clockin/timesheetentries/v1/create", body)


def get_approved_absences(employee_email: dict) -> dict:
    """ Fetch all approved absences for user """

    period_start, period_end = get_dates_range()
    body = {
        "from": period_start.date().isoformat(),
        "to": period_end.date().isoformat(),
        "employees": [employee_email],
        "absenceStatuses": ["APPROVED"],
    }

    return api_call("leave/request/v1/find-advanced", body)


def get_holidays(employee_email: str, period_start, period_end) -> list:
    """ Fetch holidays from Calamari """

    #period_start, period_end = get_dates_range()
    body = {
        "employee": employee_email,
        "from": period_start.strftime("%Y-%m-%d"),
        "to": period_end.strftime("%Y-%m-%d")
    }

    res = api_call("holiday/v1/find", body)
    return [i["start"] for i in res]


def filter_absences(employee_email: str, absences: dict, workweek: list, period_start, period_end) -> list:
    """ Filter absences from Calamari based on mail, type and holidays """

    ignored_types = settings.get("calamari_absence_ignored_types").split(",")
    holidays = get_holidays(employee_email, period_start, period_end)
    result = []
    
    for absence in absences:
        # skip specified absence types
        if absence["absenceTypeName"] in ignored_types:
            logging.debug("Skipping absence %s for %s - absence type ignored by configuration", str(absence["id"]), employee_email)
            continue

        absence_start = dt.date.fromisoformat(absence["from"])
        absence_end = dt.date.fromisoformat(absence["to"])
        absence_length = (absence_end - absence_start).days
        
        entitlements = []
        entitlement_amount = 0.0
        sanity_check_sum = 0.0
        entitlement_difference_per_day = 0.0
        non_working_days=0
        ### discover absences in 'calendar days' (include non-working-day and holidays) ###
        for i in range(absence_length + 1):
            date = absence_start + dt.timedelta(days=i)

            if date.isoformat() in holidays:
                logging.debug("Absence at %s for %s - it's a holiday", date.isoformat(), employee_email)
                non_working_days+=1
                continue
            if get_working_hours(workweek, date.strftime("%A").upper()) == 0:
                logging.debug("Absence on %s for %s - it's outside of user working week configurtation", date.isoformat(), employee_email)
                non_working_days+=1
                continue
            
            if absence['fullDayRequest'] == True:
                if absence["entitlementAmountUnit"] == "HOURS":
                    entitlement_amount = float(get_working_hours(workweek, date.strftime("%A").upper()))
                else:
                    entitlement_amount = 1.0
            else:
                if absence_start == absence_end:
                    entitlement_amount=absence['entitlementAmount']
                else:
                    if date.isoformat() == absence["from"] and absence["amountFirstDay"]:
                        entitlement_amount = float(absence["amountFirstDay"])
                    elif date.isoformat() == absence["to"] and absence["amountLastDay"]:
                        entitlement_amount = float(absence["amountLastDay"])
                    else:
                            if absence["entitlementAmountUnit"] == "HOURS":
                                entitlement_amount = float(get_working_hours(workweek, date.strftime("%A").upper()))
                            else:
                                entitlement_amount = 1.0
            
            sanity_check_sum+=entitlement_amount
            entitlements.append({
                "date": date.isoformat(),
                "amount": entitlement_amount,
            })
        
        logging.debug("Entitlement summary: %s",entitlements)
        logging.debug("Counted entitlement %f vs provided entitlement %f",sanity_check_sum, float(absence['entitlementAmount']))    
        if sanity_check_sum < float(absence['entitlementAmount']):
            entitlement_difference_per_day = (float(absence['entitlementAmount'])-sanity_check_sum)/non_working_days
        logging.debug("Entitlement difference per day %f, non working days %i",entitlement_difference_per_day, non_working_days)
        
    
        ### prepare absences list for tempo (in hours) ##
        for i in range(absence_length + 1):
            
            date = absence_start + dt.timedelta(days=i)
        
            # skip holidays and non-working days
            if (date.isoformat() in holidays) or (get_working_hours(workweek, date.strftime("%A").upper()) == 0):
                if entitlement_difference_per_day != 0.0:
                    if absence["entitlementAmountUnit"] == "HOURS":
                        hours = entitlement_difference_per_day
                    else:
                        hours = average_working_hours_per_week(workweek) # a little simplification
                        if hours is None:
                            logging.warning("Can't estimate average working hours for employee with flexible work schedule. Skipping absence for %s",date.isoformat())
                            continue
                        # hours = 8
                else:
                    logging.debug("Skipping absence at %s for %s - it's a holiday or employee non-working day", date.isoformat(), employee_email)
                    continue
            else:
                if absence['fullDayRequest'] == True:
                    hours = get_working_hours(workweek, date.strftime("%A").upper())
                else:
                    if absence["entitlementAmountUnit"] == "HOURS":
                        units=1
                    elif absence["entitlementAmountUnit"] == "DAYS":
                        units=get_working_hours(workweek, date.strftime("%A").upper())
                    else:
                        logging.error("Unknown entitlementAmountUnit")
                            
                        
                    if absence_start == absence_end:
                        hours=absence['entitlementAmount']* units
                    else:
                        if date.isoformat() == absence["from"] and absence["amountFirstDay"]:
                            hours = absence["amountFirstDay"] * units
                        elif date.isoformat() == absence["to"] and absence["amountLastDay"]:
                            hours = absence["amountLastDay"] * units
                        else:
                            hours = get_working_hours(workweek, date.strftime("%A").upper())
                
            result.append({
                "date": date.isoformat(),
                "amount": hours,
            })
    logging.debug("Result: %s", result)       
    return result
