#!/usr/bin/bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 DAASI International GmbH <info@daasi.de>

set -euo pipefail

EXTRA_FLAGS=""
RADIUS_DEBUG="${RADIUS_DEBUG:-false}"
if [ "${RADIUS_DEBUG,,}" == "true" ]; then
  EXTRA_FLAGS="-X"
fi

freeradius -l stdout -Cx && freeradius -lstdout -f $EXTRA_FLAGS
