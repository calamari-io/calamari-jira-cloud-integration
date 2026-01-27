import logging
from collections import defaultdict
from functools import cache

import requests
from requests.auth import HTTPBasicAuth

import src.utils.settings as settings
from src.utils.date import get_month_range
from src.utils.date import get_dates_range

import urllib.parse

from datetime import datetime
import time


def jira_api_call(path: str, method: str = "GET", body: dict|None = None) -> dict:
    """ Make a call to Jira API """

    url = f"{settings.get('jira_api_url')}/rest/api/3/{path}"
    auth = HTTPBasicAuth(settings.get("jira_api_user"), settings.get("jira_api_token"))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    res = requests.request(
        method, url,
        headers=headers,
        auth=auth,
        json=body,
    )
    
    logging.debug("Jira API response [%s]: %s", res.status_code, res.text)
    logging.debug("Request payload: %s",body)
    logging.debug("Request headers: %s",headers)
    
    res.raise_for_status()
    return res.json()


def tempo_api_call(path: str|None = None, method: str = "GET", body: dict|None = None, next_url: str|None = None) -> dict:
    """ Make a call to Tempo API """

    url = f"https://api.tempo.io/4/{path}" if next_url is None else next_url
    res = requests.request(
        method, url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.get('tempo_api_token')}"
        },
        json=body,
    )
    logging.debug("Tempo API response [%s]: %s", res.status_code, res.text)
    
    res.raise_for_status()
    return res.json()

@cache
def get_issue_key(issue_id: str) -> str:
    """ Get Jira Issue Kye from Issue Id """

    return jira_api_call(f"issue/{issue_id}")["key"]

@cache
def get_account_id(email: str):
    """ Get Jira Account ID from user email address """
    users = jira_api_call(f"user/search?query=" + urllib.parse.quote(email))
    if not users:
        logging.warning("User with email %s not found in Jira.", email)
        return None
    return users[0]["accountId"]

@cache
def get_user_email(account_id: str) -> str:
    """ Get user email address from Jira Account ID """

    return jira_api_call(f"user?accountId={account_id}")["emailAddress"]

def user_exists(email: str) -> bool:
    if len(jira_api_call("user/search?query="+urllib.parse.quote(email))) > 0:
        return True
    else:
        return False

def fetch_jira_worklogs(employee_email: str, account_id: str, date_from: str, date_to: str) -> list:

    # account_id = get_account_id(employee_email)
    # Format JQL to filter issues with worklogs by the user
    jql = f"worklogAuthor = {account_id} AND updated >= {date_from} AND updated <= {date_to}"
    next_token = None
    max_results = 50
    result  = []

    while True:
        # search_url = f"{jira_base_url}/rest/api/3/search"
        payload = {
            "jql": jql,
            "maxResults": max_results,
            **({"nextPageToken": next_token} if next_token else {})
            # "fields": "worklog"
        }

        # response = requests.get(search_url, headers=headers, params=params, auth=auth)
        # response.raise_for_status()
        # data = response.json()
        data = jira_api_call("search/jql","POST",payload)
        issues = data.get('issues', [])

        if not issues:
            break

        for issue in issues:
            issue_id = issue['id']
            # worklog_url = f"{jira_base_url}/rest/api/3/issue/{issue_id}/worklog"
            # wl_response = requests.get(worklog_url, headers=headers, auth=auth)
            # wl_response.raise_for_status()
            worklog_data = jira_api_call(f"issue/{issue_id}/worklog")

            for wl in worklog_data.get('worklogs', []):
                wl_author_id = wl['author']['accountId']
                started = wl['started']
                started_date = datetime.strptime(started[:10], '%Y-%m-%d').date()
                start_dt = datetime.strptime(date_from, '%Y-%m-%d').date()
                end_dt = datetime.strptime(date_to, '%Y-%m-%d').date()
                
                if wl_author_id == account_id and start_dt <= started_date <= end_dt:
                    result.append({
                        "timeSpentSeconds": wl['timeSpentSeconds'],
                        "startDate": wl['started'],
                        "accountId": wl_author_id,
                        "email": employee_email,
                        "issueKey": get_issue_key(issue_id)
                    })

        next_token = data.get("nextPageToken")
        is_last = data.get("isLast", True)

        if is_last or not next_token:
            break
        time.sleep(0.5)  # throttle to avoid API limits

    return result


def fetch_tempo_worklogs(employee_email: str, account_id: str, date_from: str, date_to: str) -> list:
    """ Fetch worklogs for user from Tempo """

    next_url = None
    result = []

    while True:
        if account_id is None:
            logging.warning("Account ID is None for email %s. Skipping Tempo worklog fetch.", employee_email)
            return result

        response = tempo_api_call(f"worklogs/user/{account_id}?from={date_from}&to={date_to}", next_url=next_url)

        for record in response["results"]:
            result.append({
                "timeSpentSeconds": record["timeSpentSeconds"],
                "startDate": record["startDate"],
                "accountId": record["author"]["accountId"],
                "email": employee_email,
                "issueKey": record["issue"]["self"],
            })

        if "metadata" not in response or "next" not in response["metadata"]:
            return result

        next_url = response["metadata"]["next"]


def sum_worklogs(worklogs: list) -> dict:
    """ Sum up the number of hours worked per day """

    result = defaultdict(lambda: 0.0)
    absence_issue = settings.get("jira_absence_issue")

    for worklog in worklogs:
        if worklog["issueKey"] == absence_issue:
            continue

        result[worklog["startDate"]] += worklog["timeSpentSeconds"] / 3600

    return result


def create_tempo_absence_worklog(
    issue_id: str, time: int, day: str, user: str
):
    """ Create worklog in Tempo """
    worklog_desc = settings.get("jira_absence_worklog_description", "Absence")
    body = {
        "issueId": issue_id,
        "timeSpentSeconds": time,
        "billableSeconds": time,
        "startDate": day,
        "startTime": "08:00:00",
        "description": worklog_desc,
        "authorAccountId": user,
    }
    return tempo_api_call("worklogs", "POST", body)

def get_jira_issue_id(issueKey):
    res = jira_api_call("issue/"+issueKey,"GET")
    logging.debug("Jira API response [%s]", res['id'])
    return res['id']

def fetch_tempo_absences(month_start=None, month_end=None) -> dict:
    """ Fetch absences from Tempo """

    issue = get_jira_issue_id(settings.get("jira_absence_issue"))
    if month_start is None or month_end is None:
        month_start, month_end = get_dates_range()
    date_filter = f"from={month_start.date().isoformat()}&to={month_end.date().isoformat()}"
    next_url = None

    results = defaultdict(lambda: [])
    while True:
        response = tempo_api_call(f"worklogs/issue/{issue}?{date_filter}", next_url=next_url)

        for record in response["results"]:
            results[get_user_email(record["author"]["accountId"])].append({
                "date": record["startDate"],
                "amount": record["timeSpentSeconds"] / 3600,
            })

        # end of the pagination
        if "metadata" not in response or "next" not in response["metadata"]:
            return results

        next_url = response["metadata"]["next"]
