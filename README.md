# Vaulty

Download videos from Vimeo and upload them to AWS Glacier vault.

## Steps

+ spawn a AWS EC2 node:
    - t2.micro (free-tier)
    - debian jessie amd64 recommended
- on the node (as admin)
    - `sudo apt update`
    - apt-install `git-core` and clone the repository: https://dev.xikolo.de/gitlab/adm/vaulty.git

    - install globally:
      - apt-install `python-setuptools`
      - change to vaulty folder and install packages:
          - `sudo python setup.py install`

    - don't install:
      - apt-install `python-pip` and run `pip install --upgrade pip`
      - change to vaulty folder and install packages:
          - `sudo pip install -r requirements.txt`
      - change to vaulty/vaulty folder and run `__init__.py`:
        - Example: `python __init__.py upload -p openhpi -v videos_openhpi_123`

## Usage

This tool provides a cli script with the commands:
```
admin@ip-172-31-31-242:~/vaulty$ vaulty --help
Usage: vaulty [OPTIONS] COMMAND [ARGS]...

Options:
  -b, --base_path TEXT  base path (default: current directory)
  --help                Show this message and exit.

Commands:
  backup_s3_bucket     download all bucket objects and upload them...
  delete_archives      delete archives from glacier vault :param...
  get_job_output       get a glacier vault job's output :param ctx:...
  get_vault_inventory  list glacier vault's archives :param ctx:...
  get_vault_jobs       list all open glacier vault's jobs :param...
  list_vaults          list all glacier vaults :param ctx: context...
  test
  upload_vimeo_videos  download videos from vimeo and upload them to...
  ```

To use the tool you need to create a credentials file that provides the AWS and 
Vimeo credentials as bash environment variables.

Create a file with the content: 
https://dev.xikolo.de/gitlab/adm/credentials/blob/master/README.md#vaulty-credentials 
and source it.

Example:
```
#!/bin/bash
export AWS_REGION=eu-central-1
export AWS_ACCESS_KEY_ID=xxxxxxxxxxxxxxxxxxxxxx
export AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxx

export VIMEO_OPENHPI_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_OPENHPI_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_OPENHPI_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxx

export VIMEO_MOOCHOUSE_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_MOOCHOUSE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_MOOCHOUSE_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxx

export VIMEO_OPENSAP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_OPENSAP_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_OPENSAP_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxx

export VIMEO_OPENWHO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_OPENWHO_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxx
export VIMEO_OPENWHO_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxx
```
The AWS credentials have to be set at least.


### Backup AWS S3 bucket
```
admin@ip-172-31-31-242:~$ vaulty backup_s3_bucket --help
Usage: vaulty backup_s3_bucket [OPTIONS]

  download all bucket objects and upload them to a glacier vault

  :param ctx: context object :param bucket_name: buckets name :return: None

Options:
  -b, --bucket_name TEXT  bucket name
  --help                  Show this message and exit.
```

The tool creates a python shelve logfile with the Galacier vault's `archiveID` and the S3 key.
The logfile is stored in the `vaultinventories` S3 bucket. This makes the deletion process much faster.


### Upload videos:
```
admin@ip-172-31-31-242:~$ vaulty upload --help
Usage: vaulty upload [OPTIONS]

  download videos from vimeo and upload them to a glacier vault

  :param ctx: context object :param platform: platform name :param
  vault_name: vault name :return: None

Options:
  -p, --platform [openhpi|opensap|moochouse]
                                  Platform
  -v, --vault_name TEXT           vault name
  --help                          Show this message and exit.
```

Before you upload the videos you should create the AWS Glacier vault (the tool 
creates the vault if not exists, but I never tested it ;)

When you down/upload the videos two python shelve files will be created. 
The shelve files stores all down-, upload informations (only readable with the 
python shelve module).

Example upload: `vaulty upload -p openhpi -v videos_openhpi_123`

Be patient, this procedure can takes some hours.


### Delete archives (with S3 logfile)
```
admin@ip-172-31-31-242:~$ vaulty delete_archives --help
Usage: vaulty delete_archives [OPTIONS]

  delete archives from glacier vault

  :param ctx: context object :param vault_name: glacier vault name :return:
  None

  - create SNS topic
  - set vault notification
  - create SQS queue
  - add permission to write to queue
  - subscribe to SNS
  - init_inventory_retrieval
  - wait for SNS/SQS nofification
  - delete Glacier vault archives

Options:
  -v, --vault_name TEXT  vault name
  -l, --logfile TEXT     logfile on S3
  --help                 Show this message and exit.
```
This approach to delete a vault's inventory requires that a python shelve logfile was created and uploaded to AWS S3 when the vault was created.
The logfile parameter is the file's name in the `vaultinventories` S3 bucket.
The logfile stores the `archiveId` of each object. The tool fetches the logfile from AWS S3 and sends for each object a delete-request to AWS Glacier.
But, every delete-request is still a Glacier job, so it can last one day until the job is done. The vault can only be deleted manually and only if the vault is empty.

Example delete archives: `vaulty delete_archives -v mammoocorg_s3bucket_backup_91095 -l mammoocorg_s3bucket_backup_91095_backup.db`

### Delete archives (without logfile)
```
admin@ip-172-31-31-242:~$ vaulty delete_archives --help
Usage: vaulty delete_archives [OPTIONS]

  delete archives from glacier vault

  :param ctx: context object :param vault_name: glacier vault name :return:
  None

  - create SNS topic
  - set vault notification
  - create SQS queue
  - add permission to write to queue
  - subscribe to SNS
  - init_inventory_retrieval
  - wait for SNS/SQS nofification
  - delete Glacier vault archives

Options:
  -v, --vault_name TEXT  vault name
  -l, --logfile TEXT     logfile on S3
  --help                 Show this message and exit.
```

Deleting Glacier vault archives happens in several steps. You have to fetch the 
vault's inventory list first to get the archives IDs. But getting the inventory 
list can take a day! So, the tool inits the inventory retrieval, gets informed 
via AWS SQS/SNS, waits for the Glacier response and deletes the archives on 
arrival.

Example delete archives: `vaulty delete_archives -v videos_openhpi_123`

*Currently, this command deletes only the archives. You have to delete the vault 
manually in the AWS console.*