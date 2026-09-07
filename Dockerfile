# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 DAASI International GmbH <info@daasi.de>

FROM debian:trixie

LABEL org.opencontainers.image.authors="DAASI International GmbH"
LABEL org.opencontainers.image.url="https://gitlab.daasi.de/edumfa/edumfa-radius"
LABEL org.opencontainers.image.version="0.0.1"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y freeradius freeradius-python3 python3 python3-requests && \
    apt-get -y autoremove && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy necessary files
COPY ./deploy/docker/entrypoint.sh /entrypoint.sh
COPY ./edumfa-radius-plugin/edumfa_radius.py /usr/share/edumfa/freeradius/edumfa_radius.py
COPY ./deploy/site_config.unlang /etc/freeradius/3.0/sites-available/edumfa

# Enable the Python module and site configuration
RUN ln -sf /etc/freeradius/3.0/mods-available/edumfa /etc/freeradius/3.0/mods-enabled/ && \
    rm -f /etc/freeradius/3.0/sites-enabled/* && \
    ln -s /etc/freeradius/3.0/sites-available/edumfa /etc/freeradius/3.0/sites-enabled/ && \
    rm -f /etc/freeradius/3.0/mods-enabled/eap

# Harden: remove freerad from superfluous groups
RUN gpasswd shadow -d freerad && gpasswd ssl-cert -d freerad

USER freerad

HEALTHCHECK CMD echo "User-Name=_dockerprobe,User-Password=pass" | radclient -r 1  localhost:1812 auth testing123 | grep '^Received Access-'

ENTRYPOINT ["/entrypoint.sh"]
