#!/usr/bin/env python

import os
import sys
import json
import time
import boto3


import logging
logger = logging.getLogger('vaulty')


def str_param(param):
    if isinstance(param, bytes):
        return str(param, 'utf-8')
    return param


class BotoClient(object):
    def __init__(self):
        self.credentials = {
            "aws_access_key_id": os.environ['aws_access_key_id'.upper()],
            "aws_secret_access_key":
                os.environ['aws_secret_access_key'.upper()],
            "region_name": os.environ['aws_region'.upper()]
        }

    def get_client(self, service_name='glacier'):
        return boto3.client(service_name, **self.credentials)


class S3(object):
    def __init__(self, boto_client):
        self.client = boto_client.get_client('s3')

    def get_bucket_name_list(self):
        return [x['Name'] for x in self.client.list_buckets()['Buckets']]

    def create_private_bucket(self, name):
        response = self.client.create_bucket(
            ACL='private',
            Bucket=str_param(name).lower(),
            CreateBucketConfiguration={
                'LocationConstraint': self.client.meta.region_name
            }
        )
        return response['ResponseMetadata']['HTTPStatusCode'] == 200

    def get_bucket_contents(self, name):
        paginator = self.client.get_paginator('list_objects')
        page_iterator = paginator.paginate(Bucket=name)

        contents = []
        for page in page_iterator:
            contents += page['Contents']
        
        return contents

    def put_object_from_data(self, bucket, key, data):
        response = self.client.put_object(
            ACL='private',
            Body=bytes(data),
            Bucket=str_param(bucket),
            Key=str_param(key)
        )
        return response

    def put_object_from_file(self, bucket, key, filepath):
        response = self.client.put_object(
            ACL='private',
            Body=open(filepath),
            Bucket=str_param(bucket),
            Key=str_param(key)
        )
        return response

    def get_object(self, bucket, key):
        return self.client.get_object(Bucket=bucket, Key=key)


class SNS(object):
    def __init__(self, boto_client):
        self.client = boto_client.get_client('sns')

    def create_sns_topic(self, name):
        response = self.client.create_topic(Name=str_param(name))
        return response['TopicArn']

    def subscribe(self, sns_topic, queue_arn):
        response = self.client.subscribe(
            TopicArn=str_param(sns_topic),
            Protocol='sqs',
            Endpoint=str_param(queue_arn)
        )
        return response['SubscriptionArn']


class SQS(object):
    def __init__(self, boto_client):
        self.client = boto_client.get_client('sqs')
        self.resource = boto3.resource('sqs', region_name=os.environ['aws_region'.upper()])

    def create_queue(self, vault_name, delay=0):
        response_create = self.client.create_queue(
            QueueName=str_param(vault_name),
            Attributes={
                'DelaySeconds': f'{delay:d}'
            }
        )

        response_attr = self.client.get_queue_attributes(
            QueueUrl=response_create['QueueUrl'],
            AttributeNames=['QueueArn'])

        return response_create['QueueUrl'], \
            response_attr['Attributes']['QueueArn']

    def set_policy(self, queue_url, queue_arn, label='SNSNotification',
                   principal='*', actions='SQS:SendMessage'):
        actions = actions.split(',')

        policy = {
            "Version": "2008-10-17",
            "Id": f"{queue_arn}/SQSDefaultPolicy",
            "Statement": [{
                "Sid": str_param(label),
                "Effect": "Allow",
                "Principal": str_param(principal),
                "Action": str_param(actions),
                "Resource": str_param(queue_arn)
            }]
        }

        return self.client.set_queue_attributes(
            QueueUrl=str_param(queue_url),
            Attributes={
                'Policy': json.dumps(policy)
            }
        )

    def receive_message(self, queue_url, callback, timeout=10):
        queue = self.resource.Queue(queue_url)

        wait = True
        while wait:
            for message in queue.receive_messages():
                message.delete()
                sns_notification = json.loads(message.body)
                callback(json.loads(sns_notification['Message']))
                wait = False
            else:
                time.sleep(timeout)


class GlacierVault(object):
    def __init__(self, boto_client):
        self.client = boto_client.get_client('glacier')

    def list_vaults(self):
        return self.client.list_vaults()['VaultList']

    def create_vault(self, vault_name):
        return self.client.create_vault(
            vaultName=str_param(vault_name)
        )

    def init_inventory_retrieval(self, vault_name):
        return self.client.initiate_job(
            vaultName=str_param(vault_name),
            jobParameters={
                'Format': 'JSON',
                'Type': 'inventory-retrieval'
            }
        )

    def get_vault_jobs(self, vault_name):
        return self.client.list_jobs(
            vaultName=str_param(vault_name)
        )

    def delete_archive(self, vault_name, archive_id):
        logger.debug(f"Delete archive {archive_id}")
        return self.client.delete_archive(
            vaultName=str_param(vault_name),
            archiveId=str_param(archive_id)
        )

    def get_job_output(self, vault_name, job_id):
        response = self.client.get_job_output(
            vaultName=str_param(vault_name),
            jobId=str_param(job_id)
        )

        return json.loads(response['body'].read())

    def set_sns_vault_notifications(
            self, vault_name, sns_topic,
            events='ArchiveRetrievalCompleted,InventoryRetrievalCompleted'):

        return self.client.set_vault_notifications(
            vaultName=str_param(vault_name),
            vaultNotificationConfig={
                'SNSTopic': str_param(sns_topic),
                'Events': events.split(',')
            }
        )

class S3Upload(object):
    def __init__(self, boto_client, bucket, logdb):
        self.client = S3(boto_client)
        self.bucket = bucket
        self.logdb = logdb

    def upload(self, key, data):
        if key not in self.logdb:
            self.logdb[key] = dict()

        logger.debug(f"Upload to S3: {key}")

        if 'response' not in self.logdb[key]:
            try:
                response = self.client.put_object_from_data(self.bucket, key, data)
                self.logdb[key]['response'] = response
            except Exception as e:
                logger.error(e)


class GlacierUpload(object):
    def __init__(self, boto_client, vault_name, logdb):
        self.client = boto_client.get_client('glacier')
        self.vault_name = vault_name
        self.logdb = logdb

    def upload(self, key, data, archive_description=None):
        if key not in self.logdb:
            self.logdb[key] = dict()

        logger.debug(f"Upload to glacier: {key}")
        archive_description = archive_description or key

        if 'response' not in self.logdb[key]:
            for i in range(1, 10):
                try:
                    response = self.client.upload_archive(
                        vaultName=self.vault_name,
                        archiveDescription=archive_description,
                        body=data
                    )
                except self.client.exceptions.RequestTimeoutException:
                    logger.error(f"Got RequestTimeoutException for {key} after {i} attempt")
                    time.sleep(1)
                    continue
                except Exception as e:
                    logger.error(f"{key} failed with error {e}")
                    break
                else:
                    self.logdb[key]['response'] = response
                    break
            else:
                logger.error(f"{key} failed after {i} attempts")
