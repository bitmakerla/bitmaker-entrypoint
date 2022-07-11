# Estela Entrypoint

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![version](https://img.shields.io/badge/version-0.1-blue)](https://github.com/bitmakerla/estela-entrypoint)
[![python-version](https://img.shields.io/badge/python-v3.10-orange)](https://www.python.org)

The package implements a wrapper layer to extract job data from environment, prepare the job properly, and execute it using Scrapy.

## Entrypoints

- `estela-crawl`: Process job args and settings to run the job with Scrapy.
- `estela-describe-project`: Print JSON-encoded project information and image metadata.

## Installation

```
$ python setup.py install 
```

## Requirements

```
$ pip install -r requirements.txt
```

## Environment variables

Job specifications are passed through env variables:

- `JOB_INFO`: Dictionary with this fields:
  - [Required] _key_: Job key (job ID, spider ID and project ID).
  - [Required] _spider_: String spider name.
  - [Required] _auth_token_: User token authentication.
  - [Required] _api_host_: API host URL.
  - [Optional] _args_: Dictionary with job arguments.
  - [Required] _collection_: String with name of collection where items will be stored.
- `KAFKA_ADVERTISED_LISTENERS`: List of advertised hosts in a comma-separated style.
- `KAFKA_ADVERTISED_PORT`: Default value: _9092_.

## Testing

```
$ pytest
```

## Formatting

```
$ black .
```
