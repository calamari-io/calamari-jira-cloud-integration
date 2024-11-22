# Calamari - Jira integration
This integration is syncing absences and timesheets between Jira and Calamari.

## Disclaimer
This repository is a fork of excelent work done in https://github.com/tenesys/calamari-jira-integration by https://tenesys.io/ team.

## How to build and run

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
Deploy using provided cloudformation template from `cloudformation/lambda.yml`. All the configuration is done using CloudFormation parameters.

## Absence sync (Calamari -> Jira)
Sync takes approved absences from Calamari and reports them as worklogs in Tempo. Worklogs are created on the issue key taken defined during deployment. During the sync, all absences are taken into account except for configured ignored employees and absence types.

Lambda will detect conflicting worklogs and log then with level WARNING to CloudWatch Logs.
