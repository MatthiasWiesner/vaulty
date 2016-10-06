# Vaulty

Download videos from Vimeo and upload them to AWS Glacier vault.

## Steps

+ spawn a AWS EC2 node:
    - t2.micro (free-tier)
    - debian jessie amd64 recommended
- on the node (as admin)
    - `sudo apt update`
    - apt-install `git-core` and clone the repository: https://dev.xikolo.de/gitlab/adm/vaulty.git
    - apt-install `python-setuptools`
    - change to vaulty folder and install packages:
        - `sudo python setup.py install`

## Usage

This tool provides a cli script wirh the commands:
```
admin@ip-172-31-31-242:~/vaulty$ vaulty --help
Usage: vaulty [OPTIONS] COMMAND [ARGS]...

Options:
  -b, --base_path TEXT  base path (default: current directory)
  --help                Show this message and exit.

Commands:
  delete_archives      delete archives from glacier vault :param...
  get_job_output       get a glacier vault job's output :param ctx:...
  get_vault_inventory  list glacier vault's archives :param ctx:...
  get_vault_jobs       list all open glacier vault's jobs :param...
  list_vaults          list all glacier vaults :param ctx: context...
  upload               download videos from vimeo and upload them to...
  ```

To use the tool you need to create a credentials file that provides the AWS and Vimeo credentials as bash environment variables.

Create a file with the content: https://dev.xikolo.de/gitlab/adm/credentials/blob/master/README.md#vaulty-credentials

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

Before you upload the videos you should create the AWS Glacier vault (the tool creates the vault if not exists, but I never tested it ;)

When you down/upload the videos to python shelve files will be created. The shelve files stores all down/upload informations (only readable with python shelve).

Example upload: `vaulty upload -p openhpi -v videos_openhpi_123`

Be patient, this procedure takes some hours.


### Delete archives
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
  --help                 Show this message and exit.
```

Deleting Glacier vault archives happens in several steps. You have to fetch the vault's inventory list first to get the archives IDs. But getting the inventory list can take a day! So, the tool inits the inventory retrieval, gets informed via AWS SQS/SNS, waits for the Glacier response and deletes the archives on arrival.

Example delete archives: `vaulty delete_archives -v videos_openhpi_123`
