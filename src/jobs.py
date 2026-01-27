import logging

import src.utils.aws as aws
import src.utils.calamari as calamari
import src.utils.jira as jira
import src.utils.settings as settings
from src.utils.date import get_month_range_yesterday
from src.utils.date import get_dates_range
from datetime import datetime


def sync_absences():
    ignored_employees = settings.get("calamari_absence_ignored_employees").split(",")
    absence_issue_id = jira.get_jira_issue_id(settings.get("jira_absence_issue"))
    month_start, month_end = get_dates_range()
    absence_worklogs = jira.fetch_tempo_absences(month_start, month_end)
    workweeks = calamari.get_workweeks()

    conflicts = {}
    for employee in calamari.get_employees():
        employee_email = employee["email"]
        employee_workweek_id = employee['workingWeek']['id']
        
        if not jira.user_exists(employee_email):
                logging.warning("User %s does not exist in jira. Skipping.", employee_email)
                continue
        
        if employee_email in ignored_employees:
            logging.debug("Ignoring absences of %s - employee ignored by configuration", employee_email)
            if employee_email in absence_worklogs:
                conflicts[employee_email] = absence_worklogs[employee_email]
            continue
        workweek=calamari.get_workweek(workweeks, employee_workweek_id)
        employee_absences = calamari.filter_absences(
            employee_email,
            calamari.get_approved_absences(employee_email),
            workweek
        )

        if employee_absences == absence_worklogs[employee_email]:
            logging.info("No conflicts for user %s", employee_email)
            continue

        logging.debug("%s %s", employee_email, employee_absences)
        for absence in employee_absences:

            # absence can span before or after synchronization period
            absence_date = datetime.strptime(absence["date"], "%Y-%m-%d")
            if absence_date < month_start:
                logging.debug("Absence date %s is < month_start (%s)", absence["date"], month_start.strftime("%Y-%m-%d"))
                absence_worklogs = jira.fetch_tempo_absences(absence_date, month_end)
            if absence_date > month_end:
                logging.debug("Absence date %s is > month_end (%s)", absence["date"], month_start.strftime("%Y-%m-%d"))
                absence_worklogs = jira.fetch_tempo_absences(month_start,absence_date)

            if absence in absence_worklogs[employee_email]:
                logging.debug("Worklog for absence of %s exists on %s", employee_email, absence["date"])
                absence_worklogs[employee_email].remove(absence)
                continue
            

            logging.info("Worklog for absence of %s is missing on %s (%s hours)", employee_email, absence["date"], absence["amount"])
            jira_account_id = jira.get_account_id(employee_email)
            jira.create_tempo_absence_worklog(absence_issue_id, absence["amount"]*3600, absence["date"], jira_account_id)

        if len(absence_worklogs[employee_email]) > 0:
            conflicts[employee_email] = absence_worklogs[employee_email]
    if len(conflicts) == 0:
        logging.info("No conflicts in worklogs detected. Well done!")
    else:
        logging.warning("Conflicting worklogs detected: %s",conflicts)
    # msg = _prepare_conflicts_message(conflicts)
    # print(msg)
    #aws.send_email("Absence sync report", msg, settings.get("notification_emails").split(","))


# def _prepare_conflicts_message(conflicts: dict) -> str:
#     message = """
#     <html>
#     <head>
#         <style>
#             .g-table {
#             border: solid 3px #DDEEEE;
#             border-collapse: collapse;
#             border-spacing: 0;
#             font: normal 14px Roboto, sans-serif;
#             }

#             .g-table th {
#             background-color: #DDEFEF;
#             border: solid 1px #DDEEEE;
#             color: #336B5B;
#             min-width: 72px;
#             padding: 10px;
#             text-align: left;
#             text-shadow: 1px 1px 1px #fff;
#             }

#             .g-table td {
#             border: solid 1px #DDEEEE;
#             color: #333;
#             padding: 10px;
#             }
#         </style>
#     </head>
#     <body>
#     <h3>Absence worklog conflicts</h3>
#     """

#     if len(conflicts) == 0:
#         message += "<p>No conflicts today!</p></body></html>"
#         return message

#     message += """
#     <table class="g-table">
#     <tr>
#         <th>Employee</th>
#         <th>Date</th>
#         <th>Amount</th>
#     </tr>
#     """

#     for email, worklogs in conflicts.items():
#         for w in worklogs:
#             message += f"""
#             <tr>
#                 <td>{email}</td>
#                 <td>{w['date']}</td>
#                 <td>{w['amount']}</td>
#             </tr>
#             """

#     message += "</table></body></html>"
#     return message


def sync_timesheets():
    contract_types = settings.get("calamari_timesheet_contract_types").split(",")
    ignored_employees = settings.get("calamari_absence_ignored_employees").split(",")

    for employee in calamari.get_employees():
        if employee["contractType"]["name"] not in contract_types:
            logging.debug("Skipping %s contract type: %s ignored by configuration", employee["email"],employee["contractType"]["name"])
            continue
        if employee["email"] in ignored_employees:
            logging.debug("Skipping %s - ignored by configuration", employee["email"])
            continue

        jira_account_id = jira.get_account_id(employee["email"])
        month_start, month_end = get_dates_range()
        if settings.get("tempo_api_token") is None or settings.get("tempo_api_token") == "":
            logging.debug("Using Jira API for fetching worklogs")
            jira_worklogs = jira.fetch_jira_worklogs(
                employee["email"], jira_account_id, month_start.date().isoformat(), month_end.date().isoformat()
            )
        else: 
            logging.debug("Using Tempo API for fetching worklogs")
            jira_worklogs = jira.fetch_tempo_worklogs(employee["email"],
                jira_account_id, month_start.date().isoformat(), month_end.date().isoformat()
            )
        #logging.debug("Jira worklogs: %s", jira_worklogs)
        calamari_timesheet = calamari.fetch_timesheets(
            employee["email"], month_start.date().isoformat(), month_end.date().isoformat()
        )
        #logging.debug("Calamari timesheets: %s", jira_worklogs)
        _compare_worklogs_with_timesheet(employee["email"], jira_worklogs, calamari_timesheet)

def _compare_worklogs_with_timesheet(employee_email: str, jira_worklogs: list, calamari_timesheet: list):
    jira_sum = jira.sum_worklogs(jira_worklogs)
    calamari_sum = calamari.sum_timesheets(calamari_timesheet)
    
    logging.debug("Jira sum: %s", jira_sum)
    logging.debug("Calamari sum: %s", calamari_sum)
    for day in jira_sum:
        if jira_sum[day]["sum"] == float(calamari_sum[day]):
            logging.info("Calamari timesheet for %s is in sync with Jira worklogs on day %s", employee_email, day)
            continue

        # remove old entry from timesheet if necessary
        if calamari_sum[day] > 0:
            for entry in calamari_timesheet:
                if day == entry["started"][0:10]:
                    logging.debug("Deleting timesheet entry for %s on day %s", employee_email, day)
                    calamari.delete_timesheet(int(entry["id"]))

        # create an entry in timesheet
        logging.info("Creating timesheet entry for %s on day %s", employee_email, day)
        projects = jira_sum[day]["projects"]
        logging.debug("Projects: %s", projects)
        # for project in projects:
        calamari.create_timesheet(employee_email, day, projects)

    for day in [d for d in calamari_sum if d not in jira_sum]:
        for worklog in calamari_timesheet:
            if day == worklog["started"][0:10]:
                logging.info("Deleting timesheet entry for %s on day %s", employee_email, day)
                calamari.delete_timesheet(int(worklog["id"]))
