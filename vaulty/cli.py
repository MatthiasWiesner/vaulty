#!/usr/bin/env python

import os
import re
from sqlite3.dbapi2 import connect
import click
import json
import sqlite3
import random
import hashlib
import logging
import smtplib
from email.message import EmailMessage


logger = logging.getLogger('vaulty')
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

import vault


def send_email(mailing_creds, subject, text):
    if not mailing_creds:
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = mailing_creds['sender']
    msg['To'] = mailing_creds['receiver']
    msg.set_content(text)

    # send email
    with smtplib.SMTP_SSL(mailing_creds['host'], mailing_creds['port']) as smtp:
        smtp.login(mailing_creds['sender'], mailing_creds['password'])
        smtp.send_message(msg)


class Vaulty(object):
    base_path = None
    boto_client = None
    mailing_creds = None

    def __init__(self, base_path, boto_client):
        if base_path and not os.path.exists(base_path):
            base_path = None
        else:
            base_path = os.path.abspath(base_path)

        self.base_path = base_path if base_path else os.path.abspath(
            os.path.curdir)
        self.boto_client = boto_client

        # mailing credentials
        self.mailing_creds = None
        mailing_creds = {
            'host': os.getenv('SMTP_HOST'),
            'port': os.getenv('SMTP_PORT', 465),
            'sender': os.getenv('SMTP_SENDER'),
            'receiver': os.getenv('SMTP_RECEIVER'),
            'password': os.getenv('SMTP_PASSWORD')
        }
        # required creds
        if mailing_creds['host'] and \
            mailing_creds['sender'] and \
            mailing_creds['receiver'] and \
            mailing_creds['password']:
            self.mailing_creds = mailing_creds


def create_sqlite_database(logdb):
    connection = sqlite3.connect(logdb)
    cursor = connection.cursor()
    cursor.execute('PRAGMA encoding = "UTF-8";')
    sql = '''
    CREATE TABLE vaultinventory(
       id VARCHAR(32) PRIMARY KEY,
       metadata TEXT
    )
    '''
    cursor.execute(sql)
    connection.commit()
    return cursor, connection

def write_record_to_database(key, metadata, cursor):
    metadata = json.dumps(metadata)

    def _tostr(param):
        if isinstance(param, bytes):
            return str(param, 'utf-8')
        return param 

    sql = f"INSERT INTO vaultinventory VALUES('{_tostr(key)}', '{_tostr(metadata)}')"
    cursor.execute(sql)
 

def delete_archives_from_logfile(boto_client, vault_name, logfile):
    s3 = vault.S3(boto_client)
    gv = vault.GlacierVault(boto_client)

    connection = sqlite3.connect(logfile)
    cursor = connection.cursor()

    sql = 'SELECT id, metadata FROM vaultinventory'
    for _, metadata_str in cursor.execute(sql):
        metadata = json.loads(metadata_str)
        archive_id = metadata['response']['archiveId']
        try:
            logger.info(gv.delete_archive(
                vault_name=vault_name,
                archive_id=archive_id
            ))
        except Exception as e:
            logger.error(f'An error occured with {archive_id}: {e}')


@click.group()
@click.option('-b', '--base_path', default='', help='base path (default: current directory)')  # nopep8
@click.pass_context
def cli(ctx, base_path):
    ctx.obj = Vaulty(base_path, vault.BotoClient())


@cli.command()
@click.option('-b', '--bucket_name', required=True, help='bucket name')
@click.pass_context
def backup_s3_bucket(ctx, bucket_name):
    """
    download all bucket objects and upload them to a glacier vault

    :param ctx: context object
    :param bucket_name: buckets name
    :return: None
    """
    s3 = vault.S3(ctx.obj.boto_client)
    bucket_list = s3.get_bucket_name_list()
    if bucket_name not in bucket_list:
        raise Exception('Bucket could not be found')

    vault_name = _clean_str(f'{bucket_name}_s3bucket_backup_{random.randint(10000, 99999)}')

    logdb_vault = {}

    glacier_vault = vault.GlacierVault(ctx.obj.boto_client)
    vaults_list = glacier_vault.list_vaults()

    if not list(filter(lambda x: x['VaultName'] == vault_name, vaults_list)):
        logger.info(f'Vault does not exist, create vault:{glacier_vault.create_vault(vault_name)}')
    else:
        raise Exception("Vault does already exist. Delete the vault and its inventory to proceed.")  # nopep8

    glacier_upload = vault.GlacierUpload(
        ctx.obj.boto_client, vault_name, logdb_vault)

    for inventory_obj in s3.get_bucket_contents(bucket_name):
        key = inventory_obj['Key']
        bucket_obj = s3.get_object(bucket_name, key)
        keyencoded = hashlib.md5(str(key).encode('utf-8')).hexdigest()

        logdb_vault[keyencoded] = dict()
        logdb_vault[keyencoded]['Key'] = str(key)
        glacier_upload.upload(keyencoded, bucket_obj['Body'].read())

    logdb_vault_name = f'{vault_name}_inventory.sqlite'
    logdb_vault_path = f'{os.getcwd()}/{logdb_vault_name}'
    logdb_vault_cursor, logdb_vault_connection = create_sqlite_database(logdb_vault_path)

    for key, metadata in logdb_vault.items():
        write_record_to_database(key, metadata, logdb_vault_cursor)
    logdb_vault_connection.commit()
    logdb_vault_cursor.close()
    logdb_vault_connection.close()


@cli.command()
@click.pass_context
def list_vaults(ctx):
    """
    list all glacier vaults

    :param ctx: context object
    :return:
    """
    for v in vault.GlacierVault(ctx.obj.boto_client).list_vaults():
        logger.info(v)


@cli.command()
@click.pass_context
def list_buckets(ctx):
    """
    list all S3 buckets

    :param ctx: context object
    :return:
    """
    s3 = vault.S3(ctx.obj.boto_client)
    for b in s3.get_bucket_name_list():
        logger.info(b)


@cli.command()
@click.option('-v', '--vault_name', required=True, help='vault name')
@click.pass_context
def get_vault_jobs(ctx, vault_name):
    """
    list all open glacier vault's jobs

    :param ctx: context object
    :param vault_name: glacier vault name
    :return: None
    """
    logger.info(vault.GlacierVault(ctx.obj.boto_client).get_vault_jobs(vault_name))


@cli.command()
@click.option('-v', '--vault_name', required=True, help='vault name')
@click.option('-j', '--job_id', required=True, help='job id')
@click.pass_context
def get_job_output(ctx, vault_name, job_id):
    """
    get a glacier vault job's output

    :param ctx: context object
    :param vault_name: glacier vault name
    :param job_id: glacier vault job id
    :return: None
    """
    logger.info(vault.GlacierVault(ctx.obj.boto_client).get_job_output(
        vault_name, job_id))


@cli.command()
@click.option('-v', '--vault_name', required=True, help='vault name')
@click.option('-l', '--logfile', required=False, help='Sqlite logfile')
@click.pass_context
def delete_archives(ctx, vault_name, logfile=None):
    """
    delete archives from glacier vault

    :param ctx: context object
    :param vault_name: glacier vault name
    :return: None

    - create SNS topic

    - set vault notification

    - create SQS queue

    - add permission to write to queue

    - subscribe to SNS

    - init_inventory_retrieval

    - wait for SNS/SQS nofification

    - delete Glacier vault archives
    """
    if logfile:
        delete_archives_from_logfile(ctx.obj.boto_client, vault_name, logfile)
        return

    sns = vault.SNS(ctx.obj.boto_client)
    sqs = vault.SQS(ctx.obj.boto_client)
    gv = vault.GlacierVault(ctx.obj.boto_client)

    sns_topic_arn = sns.create_sns_topic(_clean_str(vault_name))
    gv.set_sns_vault_notifications(vault_name, sns_topic_arn)

    sqs_queue_url, sqs_queue_arn = sqs.create_queue(_clean_str(vault_name), delay=0)
    sqs.set_policy(sqs_queue_url, sqs_queue_arn)
    sns_subscription_arn = sns.subscribe(sns_topic_arn, sqs_queue_arn)

    logger.info({
        "SNS_TopicArn": sns_topic_arn,
        "SNS_SubscriptionArn": sns_subscription_arn,
        "SQS_QueueuUrl": sqs_queue_url,
        "SQS_QueueuArn": sqs_queue_arn
    })

    logger.info(gv.init_inventory_retrieval(vault_name))

    def handle_sns_notification(sns_notification):
        send_email(ctx.obj.mailing_creds, 'Vaulty: delete_archives - start', 
f'''
SNS-Notification arrived!

vault:  {vault_name}
job-id: {job_id}
''')
        job_id = sns_notification['JobId']
        job_output = gv.get_job_output(vault_name, job_id)

        for archive in job_output['ArchiveList']:
            archive_id = archive['ArchiveId']
            logger.info(f"DELETE {archive_id} from {vault_name}")
            logger.info(gv.delete_archive(
                vault_name=vault_name,
                archive_id=archive_id
            ))
        
        gv.delete_vault(vault_name)
        send_email(ctx.obj.mailing_creds, 'Vaulty: delete_archives - complete', 
f'''
Deletion complete!

vault:  {vault_name}
job-id: {job_id}
''')

    sqs.receive_message(sqs_queue_url, handle_sns_notification)


@cli.command()
@click.option('-v', '--vault_name',required=True, help='vault name')  # nopep8
@click.pass_context
def get_vault_inventory(ctx, vault_name):
    """
    list glacier vault's archives

    :param ctx: context object
    :param vault_name: vault name
    :return: None
    """
    sns = vault.SNS(ctx.obj.boto_client)
    sqs = vault.SQS(ctx.obj.boto_client)
    gv = vault.GlacierVault(ctx.obj.boto_client)

    sns_topic_arn = sns.create_sns_topic(_clean_str(vault_name))
    gv.set_sns_vault_notifications(vault_name, sns_topic_arn)

    sqs_queue_url, sqs_queue_arn = sqs.create_queue(_clean_str(vault_name), delay=0)
    sqs.set_policy(sqs_queue_url, sqs_queue_arn)
    sns_subscription_arn = sns.subscribe(sns_topic_arn, sqs_queue_arn)

    logger.info({
        "SNS_TopicArn": sns_topic_arn,
        "SNS_SubscriptionArn": sns_subscription_arn,
        "SQS_QueueuUrl": sqs_queue_url,
        "SQS_QueueuArn": sqs_queue_arn,
    })

    logger.info(gv.init_inventory_retrieval(vault_name))

    def handle_sns_notification(sns_notification):
        job_id = sns_notification['JobId']
        job_output = gv.get_job_output(vault_name, job_id)

        cursor, connection = create_sqlite_database(f'{vault_name}_inventory.sqlite')
        for archive in job_output['ArchiveList']:
            write_record_to_database(archive['ArchiveId'], archive, cursor)
        cursor.close()
        connection.close()

    sqs.receive_message(sqs_queue_url, handle_sns_notification)


def _clean_str(s):
    return re.sub('[^a-zA-Z0-9_-]', '', s)


if __name__ == '__main__':
    cli()
