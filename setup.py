#!/usr/bin/python3

import ramp_experiment
import setuptools

with open("README.md", "r") as fd:
    long_description = fd.read()

setuptools.setup(
    name="ramp_experiment",
    license="LICENSE",
    version=ramp_experiment.__version__,
    author=ramp_experiment.__author__,
    author_email=ramp_experiment.__email__,
    description="remote experiment consisting of a adjustable ramp and a ball",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=ramp_experiment.__contact__,
    packages=["ramp_experiment"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
    python_requires='>=3.6.1'
)
