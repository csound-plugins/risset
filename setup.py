from setuptools import setup

long_description = """
# Csound Package Manager


"""

setup(
    name = "risset",
    version = "0.0.1",
    description = "A package manager for csound",
    author = "Eduardo Moguillansky",
    long_description = long_description,
    long_description_content_type='text/markdown',
    scripts=['risset']    
)