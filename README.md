<!--
SPDX-FileCopyrightText: 2025 DAASI International GmbH <info@daasi.de>
SPDX-License-Identifier: Apache-2.0
-->

# edumfa-radius
This repository contains the eduMFA plugin for FreeRADIUS. It can be installed
onto an existing FreeRADIUS 3.x installation or used as a container.  

## Installation (Docker)
TODO

## Installation (Module)

TODO

# Maintenance
TODO for upstream

## Run tests

`uv run --with-requirements tests/requirements.txt pytest`  
To use your own build of edumfa-radius, you can set it as a environment
variable: `EDUMFA_RADIUS_TEST_IMAGE="mynamespace/myrepo:mytag" uv run [..]`


## eduMFA update
If there is a new eduMFA version released, do:
1. Update the version in:

- `/tests/test_auth.py`
- `/deploy/docker-example/docker-compose.yml`

2. Run the test to make sure everything is working: `uv run --with-requirements requirements.txt pytest`
3. Create a PR with your changes.

OS and FreeRADIUS updates are handled by floating tags and automatic rebuilds. TODO upstream  

## New version

Update version in:
- `Dockerfile`
- `edumfa-radius-plugin/edumfa_radius.py`
