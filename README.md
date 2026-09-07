<!--
SPDX-FileCopyrightText: 2025 DAASI International GmbH <info@daasi.de>
SPDX-License-Identifier: Apache-2.0
-->

# edumfa-radius
This repository contains the eduMFA plugin for FreeRADIUS. It can be installed
onto an existing FreeRADIUS 3.x installation or used as a container.  

## Installation (Docker)

The
[edumfa-radius](https://github.com/edumfa/eduMFA/pkgs/container/edumfa-radius)
image is a FreeRADIUS container image with this plugin pre-installed.  
To get it to work, you need to:
1. Provide a config for the edumfa-radius module.
- Copy and edit [/deploy/mod_config.unlang](/deploy/mod_config.unlang).
- Mount it into your container at `/etc/freeradius/3.0/mods-available/edumfa`.
2. Provide a clients config for FreeRADIUS.
- Copy and edit [/deploy/docker-example/clients.conf](/deploy/docker-example/clients.conf).
- Mount it into your container at `/etc/freeradius/3.0/clients.conf`.

You can also pass the environment variable `RADIUS_DEBUG=true` to enable debug
output.  
For an example, see [/deploy/docker-example/](/deploy/docker-example/).

> [!IMPORTANT]
> It is strongly recommended to define a
  [pull policy](https://docs.docker.com/reference/compose-file/services/#pull_policy)
  for the edumfa-radius service. The tag of the most recent release gets rebuilt
  daily to incorporate updates to the Debian base (including FreeRADIUS).

### Upgrading
Update by using the newer tag. Please do so as early as possible, since only the
most recent tag receives updates for the base image. Read the
[CHANGELOG.md](CHANGELOG.md) before updating.  
The version numbers follow [semantic versioning](https://semver.org/).


## Installation (Module)

1. Install FreeRADIUS, Python3, and python-requests. Example for Debian:
   `apt install freeradius freeradius-python3 python3 python3-requests`
2. Install the FreeRADIUS module:
- Edit the settings at [/deploy/mod_config.unlang](/deploy/mod_config.unlang).
- Copy the file to `/etc/freeradius/3.0/mods-available/edumfa`.
- Enable the module:
   `ln -s /etc/freeradius/3.0/mods-available/edumfa /etc/freeradius/3.0/mods-enabled/edumfa`
3. Configure your site to use the new module
- If you already have a site, take a look at [/deploy/site_config.unlang](/deploy/site_config.unlang) and
  incorporate it into your existing configuration.
- If not:
  + Copy that file to `/etc/freeradius/3.0/sites-available/edumfa`.
  + Disable all default sites by deleting all files in
    `/etc/freeradius/3.0/sites-enabled/`.
  + Enable the edumfa site:
   `ln -s /etc/freeradius/3.0/sites-available/edumfa /etc/freeradius/3.0/sites-enabled/edumfa`
4. Copy
   [edumfa-radius-plugin/edumfa_radius.py](edumfa-radius-plugin/edumfa_radius.py)
   to `/usr/share/edumfa/freeradius/edumfa_radius.py`. If you prefer a different
   path, edit the `python_path` in the module config.
5. Don't forget to configure your clients (`/etc/freeradius/3.0/clients.conf`).

Restart FreeRADIUS.  
If something goes wrong, enable FreeRADIUS debugging. As a general hint, this
can be done by restarting the server with the "-X" flag. 

## Testing it out
To test if everything is working, you can use `radclient`. Example command with
the default clients.conf and the server on `localhost`:  
`echo "User-Name=myuser,User-Password=mypassword123123" | radclient -x localhost:1812 auth testing123`  
If you receive an Access-Challenge, you can pass back the State in the next
request to simulate a Challenge-Response authentication:  
`echo "User-Name=myuser,User-Password=123123,State=0x3133383732323037343332393535333930323031" | radclient -x localhost:1812 auth testing123`  
If something goes wrong, enable debugging and retry.

### Upgrading
Upgrade the script by replacing it with the new version. Read the
[CHANGELOG.md](CHANGELOG.md) before updating.  
The version numbers follow [semantic versioning](https://semver.org/).

# Maintenance
This repository is maintained by DAASI International GmbH.

## Run tests

`uv run --with-requirements tests/requirements.txt pytest`  
To use your own build of edumfa-radius, you can set it as a environment
variable: `EDUMFA_RADIUS_TEST_IMAGE="mynamespace/myrepo:mytag" uv run [..]`


## eduMFA update
If there is a new eduMFA version released, do:
1. Update the version in:

- `/tests/test_auth.py`
- `/deploy/docker-example/docker-compose.yml`

2. Run the tests to make sure everything is working.
3. Create a PR with your changes.

This makes sure that edumfa-radius works with the latest eduMFA version.  
OS and FreeRADIUS updates in the image are handled by daily rebuilds.

## Release of a new version

1. Follow the "Release Prozess für didmos" article in the Wiki.
2. In the "changelog step":
- Update the version number in the following files:
  + `Dockerfile`
  + `edumfa-radius-plugin/edumfa_radius.py`
- Update the versions in `tests/requirements.txt`.
- Run the tests.
3. After the "Release Prozess für didmos", make sure the pipeline runs
   successfully.
