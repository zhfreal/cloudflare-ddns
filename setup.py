#!/usr/bin/env python3
# cython: language_level=3

from setuptools import setup, find_packages

# Read requirements from requirements.txt
# with open('requirements.txt', 'r') as f:
#     requirements = f.read().splitlines()

setup(
    name="cloudflare-ddns",
    version="2.11.1",
    author='zhfreal',
    author_email='zhfreal@gmail.com',
    description='maintain cloudflare ddns records',
    keywords='cloudflare, ddns, records',
    long_description="list domains, list records, add , update or delete records",
    long_description_content_type='text/markdown',
    url='https://github.com/zhfreal/cloudflare-ddns',
    project_urls={
        'Documentation': 'https://github.com/zhfreal/cloudflare-ddns',
        'Bug Reports':
            'https://github.com/zhfreal/cloudflare-ddns/issues',
        'Source Code': 'https://github.com/zhfreal/cloudflare-ddns',
        # 'Funding': '',
        # 'Say Thanks!': '',
    },
    packages=find_packages(),
    install_requires=[
        'requests >= 2.27.0',
        'gevent >= 21.8.0'
    ],
    entry_points={
        'console_scripts': [
            # 'command-name=module.submodule:function'
            'cloudflare-ddns=src.cloudflare_ddns:main',
        ],
    },
)
