#! /usr/bin/env python
# encoding: utf-8

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='vaulty',
    version='0.1.0',
    description='Download videos from vimeo and stores them into a glacier vault.',
    author='openHPI',
    packages=['vaulty'],
    install_requires=[
        'boto3',
        'click',
        'requests',
        'PyVimeo==0.3.6'
    ],
    entry_points='''
        [console_scripts]
        vaulty=vaulty:cli
    ''',
)
