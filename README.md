# Vaulty

Handle some operation with AWS Glacier vault.

On Amazon AWS, there are the low-cost S3 Glacier Vaults. 
Any files can be stored in these. However, accessing the contents of a vault 
is somewhat cumbersome. This is especially true for deleting a vault. 
Only after all the contents of a vault have been deleted can the vault itself 
be deleted. Unfortunately, the AWS Management Console does not offer the 
option to delete all content. This must be done using the REST API, the 
AWS SDK for Python, the AWS SDK for Java, the AWS SDK for .NET or the AWS CLI. 
The script creates a "give-me-the-content" job, via SQS and SNS the script 
waits for the answer and then deletes the archives. The deletion of the 
content of a vault contents can take 24 hours (or longer), so it is advisable 
to perform the deletion process in a linux screen.

Furthermore, the script can also be used to create a vault for an S3 bucket.

## Steps

+ spawn a AWS EC2 node:
    - t2.micro (Ubuntu or Debian with python3, free-tier)
- on the node (as admin)
    - `sudo apt update`
    - `apt install git-core` and clone the repository: https://github.com/MatthiasWiesner/vaulty.git
    - python:
      - `pip install pipenv` (add `~/.local/bin` to you `PATH` variable)
      - change to vaulty folder and install packages:
          - `pipenv install`
- create a `.env` file in vaulty folder with AWS credentials
```
#!/bin/bash
export AWS_REGION=eu-central-1
export AWS_ACCESS_KEY_ID=xxxxxxxxxxxxxxxxxxxxxx
export AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxx
```
### Mailing
To get informed about the long running `delete-archives` job, add to `.env`:
```
export SMTP_HOST=smtp.example.com
export SMTP_PORT=465
export SMTP_RECEIVER=receiver@exmaple.com
export SMTP_SENDER=sender@example.com
export SMTP_PASSWORD=xxxxxxxxxxxxxxxxxxxxxx
```
For smtp.gmail.com you need an extra app-password

## Usage

This tool provides a cli script with the commands:
```
> screen -S deletevault -L -Logfile deletevault.log
> cd vaulty
> pipenv shell
> source .env
> python3 vaulty/cli.py --help
Usage: cli.py [OPTIONS] COMMAND [ARGS]...

Options:
  -b, --base_path TEXT  base path (default: current directory)
  --help                Show this message and exit.

Commands:
  backup-s3-bucket     download all bucket objects and upload them to a...
  delete-archives      delete archives and the vault from glacier vault
  get-job-output       get a glacier vault job's output
  get-vault-inventory  list glacier vault's archives
  get-vault-jobs       list all open glacier vault's jobs
  list-buckets         list all S3 buckets
  list-vaults          list all glacier vaults

# detach from screen by hitting [ctrl] + [a] + [d]
  ```