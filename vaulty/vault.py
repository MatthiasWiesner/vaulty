#!/usr/bin/env python

import os
import sys
import json
import time
import boto3


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


class SNS(object):
    def __init__(self, boto_client):
        self.client = boto_client.get_client('sns')

    def create_sns_topic(self, name):
        response = self.client.create_topic(Name=name)
        return response['TopicArn']

    def subscribe(self, sns_topic, queue_arn):
        response = self.client.subscribe(
            TopicArn=sns_topic,
            Protocol='sqs',
            Endpoint=queue_arn
        )
        return response['SubscriptionArn']


class SQS(object):
    def __init__(self, boto_client):
        self.client = boto_client.get_client('sqs')
        self.resource = boto3.resource('sqs', region_name=os.environ['aws_region'.upper()])

    def create_queue(self, vault_name, delay=0):
        response_create = self.client.create_queue(
            QueueName=vault_name,
            Attributes={
                'DelaySeconds': '%d' % delay
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
            "Id": "%s/SQSDefaultPolicy" % queue_arn,
            "Statement": [{
                "Sid": label,
                "Effect": "Allow",
                "Principal": principal,
                "Action": actions,
                "Resource": queue_arn
            }]
        }

        return self.client.set_queue_attributes(
            QueueUrl=queue_url,
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
            vaultName=vault_name
        )

    def init_inventory_retrieval(self, vault_name):
        return self.client.initiate_job(
            vaultName=vault_name,
            jobParameters={
                'Format': 'JSON',
                'Type': 'inventory-retrieval'
            }
        )

    def get_vault_jobs(self, vault_name):
        return self.client.list_jobs(
            vaultName=vault_name
        )

    def delete_archive(self, vault_name, archive_id):
        return self.client.delete_archive(
            vaultName=vault_name,
            archiveId=archive_id
        )

    def get_job_output(self, vault_name, job_id):
        response = self.client.get_job_output(
            vaultName=vault_name,
            jobId=job_id
        )

        return json.loads(response['body'].read())

    def set_sns_vault_notifications(
            self, vault_name, sns_topic,
            events='ArchiveRetrievalCompleted,InventoryRetrievalCompleted'):

        return self.client.set_vault_notifications(
            vaultName=vault_name,
            vaultNotificationConfig={
                'SNSTopic': sns_topic,
                'Events': events.split(',')
            }
        )


class GlacierUpload(object):
    def __init__(self, boto_client, vault_name, logdb):
        self.client = boto_client.get_client('glacier')
        self.vault_name = vault_name
        self.logdb = logdb

    def upload(self, archive_id, filepath):
        if archive_id not in self.logdb:
            for i in range(1..10):
                try:
                    response = self.client.upload_archive(
                        vaultName=self.vault_name,
                        archiveDescription=archive_id,
                        body=open(filepath)
                    )
                except self.client.exceptions.RequestTimeoutException:
                    print >> sys.stderr, "Got RequestTimeoutException for %s after %d attempt" % (  # nopep8
                        archive_id, i)
                    time.sleep(1)
                    continue
                except Exception as e:
                    print >> sys.stderr, "%s failed with error %s" % (
                        archive_id, str(e))
                    break
                else:
                    self.logdb[archive_id] = dict(
                        response=response
                    )
                    break
            else:
                print >> sys.stderr, "%s failed after %d attempts" % (
                        archive_id, i)
