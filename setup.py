#!/usr/bin/env python3
# cython: language_level=3

from setuptools import setup

setup(
    name='cloudflare-ddns',
    version="2.8.0",
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
    install_requires=[
        'requests>=2.27.0',
        'gevent>=21.8.0'
    ],
    # package_dir={'': 'src'},
    packages=['src'],
    classifiers=[
        # see https://pypi.org/classifiers/
        'Development Status :: 5 - Production/Stable',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3 :: Only',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    entry_points={
        'console_scripts': [
            'cloudflare-ddns=src.cloudflare_ddns:main']
    },
    python_requires='>=3.8',
    # install_requires=['Pillow'],
    extras_require={
        'dev': ['check-manifest'],
        # 'test': ['coverage'],
    },
)
