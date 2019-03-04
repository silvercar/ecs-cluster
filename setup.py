import os
from setuptools import setup, find_packages

install_requires = [
    'boto3',
    'click',
    'polling',
    'requests',
    'paramiko'
]

test_requires = []


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='ecs-cluster',
    version='1.1.1.test-deploy-gemfury.2',
    author='Silvercar',
    author_email="info@silvercar.com",
    url='https://github.com/silvercar/ecs-cluster',
    description='Tools for working with AWS ECS clusters',
    license='Apache 2.0',
    keywords='aws ecs',
    long_description=read('README.md'),
    install_requires=install_requires,
    tests_require=test_requires,
    package_dir={'': 'src'},
    packages=find_packages('src'),
    include_package_data=True,
    entry_points={
        'console_scripts': {
            'ecs-cluster = ecs_cluster.main:cli'
        }
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Topic :: Utilities',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
)
