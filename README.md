# Calamari - Jira integration
This integration is syncing absences between Calamari and Jira Tempo.

## Disclaimer
This repository is a fork of excellent work done by [Tenesys](https://tenesys.io) team in  [calamari-jira-integration](https://github.com/tenesys/calamari-jira-integration) repository, with a few improvements. 

## Deployment

### Build 
```
pip3 install -r requirements.txt -t build
cp -r src build
cd build
zip -r ../build.zip .
```

### Upload to AWS S3 bucket
You can use AWS Management Console or `awscli`

```
aws s3 cp build.zip s3://<yourbucketname>/
```

### Deploy using Cloudformation template
Deploy using the CloudFormation template provided in `cloudformation/lambda.yml`. All configuration is done using CloudFormation parameters and can be stored in the SSM Parameter Store or as Lambda function environment variables.

| Parameter Name | Description | Example | Default value |
| :------------- | :---------- | :------ | :------------ |
| `S3Bucket` | S3 bucket that will contain Lambda code. It needs to be in the same region as Lambda. | my-lambda-code-bucket | N/A |
| `S3BucketKey` | Path to the zip.ed Lambda code | `build.zip` or `somedirectory/build.zip` | `build.zip` | 
| `LambdaHandlerPath` | Default lambda function. Change the default value ONLY if you have modified the code. | `src/main.lambda_handler` | `src/main.lambda_handler` |
| `UseSSMParameterStore` | Set to `True` if you want to keep all Lambda configurations in SSM Parameter Store. Otherwise configuration will be stored in Lambda environment variables | `True` | `False` |
| `SSMParameterStorePrefix` | Is used if `UseSSMParameterStore` is set to `True`. Define the prefix for configuration stored in SSM Parameter store. | `/my-configuration-prefix` | `/calamari-jira-cloud-integration` |
| `AbsenceSyncCrontabDefinition` | Cron-based schedule definition for absence (Calamari -> Tempo) synchronization. More information can be found [here](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html). Leave empty to disable this type of synchronization. | `*/3 * * * ? *` (every 3 minutes) | `* 20 * * ? *` (every day at 8 p.m.) |
| `TimesheetSyncCrontabDefinition` | Cron-based schedule definition for timesheet (Tempo -> Calamari) synchronization. More information can be found [here](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html). Leave empty to disable this type of synchronization. | `*/3 * * * ? *` (every 3 minutes) | `* 20 * * ? *` (every day at 8 p.m.) |
| `CalamariAbsenceIgnoredEmployees` | Comma-separated list of employees email that should be ignored during synchronization. Leave default value if none. | `my.employee@mycompany.org` | `employee@company.com` |
| `CalamariAbsenceIgnoredTypes` | Comma-separated list of calamari.io absence types that should be ignored during synchronization. (Calamari -> Tempo) | `Remote work` | `Praca zdalna,Delegacja` |
| `CalamariApiToken` | calamari.io API token. More information can be found [here](https://help.calamari.io/en/articles/24539-what-is-the-api-key-for-and-where-can-i-find-it). | N/A | N/A |
| `CalamariApiUrl` | Your dedicated calamari API Base URL. | https://mycompany.calamari.io | N/A |
| `CalamariTimesheetContractTypes` | Comma-separated list of contract types. Only users with those contract type(s) will have work synchronized (Tempo -> Calamari). | `Umowa o pracę - 26 dni` | `Umowa o pracę - 26 dni` |
| `JiraAbsenceIssue` | Jira issue name to store absences as Tempo work logs | `LEAVE-1` | N/A |
| `JiraAbsenceWorklogDescription` | Description that will be used for all Tempo work logs. | `Holiday/Vacation/Leave` | N/A |
| `JiraApiUrl` | Jira API URL | `https://my-company.atlassian.net` | N/A |
| `JiraApiToken` | Jira API token [https//id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens). | N/A | N/A |
| `JiraApiUser` | Jira API user (email). It need to have permission to log work as other users and permission to issue selected in `JiraAbsenceIssue` | N/A | N/A |
| `TempoApiToken` | Tempo API token. Can be generated in Tempo Configuration -> Data Access -> API Integration. Leave empty for native Jira worklogs. | N/A | N/A |
| `DaysAfter` | How many days in the past should be take into consideration during the synchronization process. Maximum value is 90. | `14` | `30` | 
| `DaysBefore` | How many days in the future should be taken into consideration during synchronization process. Maximum value is 90. | `14` | `30` | 
| `Debug` | Set to 1 to enable Lambda debug logging (CloudWatch Logs) | `1` | `0` |

## How it works

## Absence sync (Calamari -> Jira)
Synchronization will take approved absences from Calamari and report them as work logs in Tempo. Abseces are stored as Tempo work logs in issue defined by `JiraAbsenceIssue`. During the synchronization, all absences are taken into account except for:
*  ignored employees (`CalamariAbsenceIgnoredEmployees`)
*  ignored absence types (`CalamariAbsenceIgnoredTypes`)

Lambda will detect conflicting work logs and log them with level WARNING to CloudWatch Logs.

## Timesheet sync (Jira Worklogs or Tempo Worklogs -> Calamari)
If a `TempoApiToken` is provided, the synchronization will use Tempo worklogs and add them as shifts in Calamari. Otherwise, it will use native Jira worklogs.

Worklogs will only be added for employees with the selected contract type(s) (`CalamariTimesheetContractTypes`).

All conflicts will be overwritten by data from Jira/Tempo Worklogs.

## How it works

### Visibility of users’ email addresses

To correctly map user accounts between Jira and Calamari, email address visibility must be enabled in Jira in both places:

* System → General configuration → Options → User email visibility → Show

* User profile → Profile and visibility → Contact → Anyone

This ensures that email addresses are visible and can be used to match user accounts between Jira and Calamari.
