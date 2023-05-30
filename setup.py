from setuptools import setup
import subprocess
import sys

if (sys.version_info.major, sys.version_info.minor) < (3, 7):
    print("Python >= 3.8 required")
    sys.exit(-1)

long_description = open("README.md").read()
version = subprocess.check_output([sys.executable, "risset.py", "--version"]).decode('utf8').strip()


setup(
    name = "risset",
    version = version,
    python_requires = ">=3.8",
    description = "A package manager for csound",
    author = "Eduardo Moguillansky",
    author_email = "eduardo.moguillansky@gmail.com",
    long_description = long_description,
    long_description_content_type = 'text/markdown',
    py_modules=["risset"],

    url="https://github.com/csound-plugins/risset",

    install_requires=[
        'pygments',
        'ctcsound7>=0.3.0',
        'mkdocs'
    ],

    entry_points={
        "console_scripts": [
            "risset=risset:main",
        ]
    }
)
