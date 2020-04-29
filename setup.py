from setuptools import setup
import subprocess
import sys

long_description = open("README.md").read()
version = subprocess.getoutput("python3 ./risset --version")

setup(
    name = "risset",
    version = version,
    description = "A package manager for csound",
    author = "Eduardo Moguillansky",
    long_description = long_description,
    long_description_content_type='text/markdown',
    scripts=['risset']    
)