#######################################################################
# Copyright: DAASI International GmbH 2026.
#
# This is Open Source Software
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 DAASI International GmbH <info@daasi.de>
# See https://www.apache.org/licenses/LICENSE-2.0
#
# Author: Aleyna Nasher Taher, DAASI International GmbH, www.daasi.de
# For questions please mail to info@daasi.de
#######################################################################

# Dear user, please use a non-develop version. You can select a tag on the upper
# left drop-down.
VERSION="develop"

import json
import re
import ssl
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Imports all constants (return codes and log levels) as well as the radlog
# function. See: `/src/modules/rlm_python3/radiusd.py` in the freeradius-server
# repository.
# It also gets injected with the config defined in the mod file. It can be
# found at radiusd.config and is a Dict[str, str].
try:
    import radiusd
except ModuleNotFoundError:
    if __name__ != "__main__":
        raise
    # Create a fake radius class to be able to run this from the CLI.
    class radiusd:
        def radlog(level: int, message: str) -> None:
            print(f"{level}: {message}")

        RLM_MODULE_REJECT = 0
        RLM_MODULE_FAIL = 1
        RLM_MODULE_OK = 2
        RLM_MODULE_HANDLED = 3
        RLM_MODULE_INVALID = 4
        RLM_MODULE_USERLOCK = 5
        RLM_MODULE_NOTFOUND = 6
        RLM_MODULE_NOOP = 7
        RLM_MODULE_UPDATED = 8
        RLM_MODULE_NUMCODES = 9

        # from log.h
        L_AUTH = 2
        L_INFO = 3
        L_ERR = 4
        L_WARN = 5
        L_PROXY = 6
        L_ACCT = 7

        L_DBG = 16
        L_DBG_WARN = 17
        L_DBG_ERR = 18
        L_DBG_WARN_REQ = 19
        L_DBG_ERR_REQ = 20
        config = {
            "url": "http://localhost:8000/validate/check",
            "ssl_check": "false",
        }
        radlog(1, "Dummy radiusd loaded")

radlog = radiusd.radlog
L_INFO = radiusd.L_INFO
L_DBG = radiusd.L_DBG
L_ERR = radiusd.L_ERR


import requests

DEFAULTS = {
    "url": "",
    "realm": "",
    "clientattribute": "",
    "ssl_check": "true",
    "timeout": 10,
    "pass_split_null_byte": "false",
    "add_empty_pass": "false",
}
# The configuration as loaded by _load_config.
config = None


# FreeRADIUS return codes as Enum (for easier logging)
class ReturnCode(Enum):
    RLM_MODULE_REJECT = radiusd.RLM_MODULE_REJECT  # immediately reject the request
    RLM_MODULE_FAIL = radiusd.RLM_MODULE_FAIL  # module failed, don't reply
    RLM_MODULE_OK = radiusd.RLM_MODULE_OK  # the module is OK, continue
    RLM_MODULE_HANDLED = radiusd.RLM_MODULE_HANDLED  # the module handled the request, so stop.
    RLM_MODULE_INVALID = radiusd.RLM_MODULE_INVALID  # the module considers the request invalid.
    RLM_MODULE_USERLOCK = radiusd.RLM_MODULE_USERLOCK  # reject the request (user is locked out)
    RLM_MODULE_NOTFOUND = radiusd.RLM_MODULE_NOTFOUND  # user not found
    RLM_MODULE_NOOP = radiusd.RLM_MODULE_NOOP  # module succeeded without doing anything
    RLM_MODULE_UPDATED = radiusd.RLM_MODULE_UPDATED  # OK (pairs modified)
    RLM_MODULE_NUMCODES = radiusd.RLM_MODULE_NUMCODES  # How many return codes there are


# Maximum lengths for input validation
MAX_USERNAME_LENGTH = 253
MAX_PASSWORD_LENGTH = 128
MAX_STATE_LENGTH = 256


def _censor(censor_me: dict) -> dict:
    """Copies the input dictionary and censors any password fields.

    :param censor_me: The dictionary to copy and censor.
    :return: The copied and censored dictionary.
    """
    censored = censor_me.copy()
    known_fields = ("pass", "user-password", "chap-password")
    for key, value in censored.items():
        if key.lower() in known_fields:
            censored[key] = "__CENSORED__"
    return censored


def _return_freeradius_format(
    return_code: ReturnCode, reply_items: Dict[str, Any]
) -> Tuple[int, Tuple, Tuple]:
    """Returns in a format which rlm_python3 expects.

    https://wiki.freeradius.org/modules/Rlm_python says:
    > There are three possible return values: None (which is the same as
    returning radiusd.RLM_MODULE_OK), an integer (preferable using the
    radiusd.RLM_MODULE_* constants) and a tuple of size 3: first element is the
    integer return, second argument is a tuple to update reply, third argument
    is a tuple to update config. Those tuples use the same format as mentioned
    above.

    This function returns as a tuple of size 3.

    :param return_code: The ReturnCode to return.
    :param reply_items: Which items to add to the reply.
    :return: The tuple in the format expected by rlm_python3.
    """
    return (return_code.value, _build_reply(reply_items), ())


def _get_or_dict(obj: dict, key: str) -> Any:
    """Does `.get(key)`, but if the key does not exist or the value is None
    return an empty dictionary.
    This ensure chained gets don't fail, if a key have None as its value, since
    `{"mykey": None}.get("mykey", mydefaultvalue)` returns None.

    :param obj: The dictionary to get the value from.
    :param key: The key to get from the dictionary.
    :return: The value of the dict or an empty dictionary
    """
    value = obj.get(key, None)
    if value is None:
        return {}
    else:
        return value


def _validate_url(url: str, ssl_check: bool) -> bool:
    """Validate that a URL is properly formatted and uses HTTPS if SSL verification is enabled.

    :param url: URL to check.
    :param ssl_check: The ssl_check setting from the config.
    :return: True if the URL is valid, else False."""
    if not url:
        return False

    try:
        parsed = requests.utils.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        # If SSL verification is enabled, ensure HTTPS is used
        if ssl_check and parsed.scheme != "https":
            radlog(
                L_ERR,
                f"URL uses {parsed.scheme} but SSL_CHECK is enabled. HTTPS is required.",
            )
            return False

        return True
    except Exception:
        return False


def _load_config(config: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """This function validates the config and returns a new dict if it is valid.
    It also transforms data types as rlm_python3 only gives us strings.

    :param config: The config to parse, likely radiusd.config.
    :return: The parsed config as dict or None if parsing failed.
    """
    cfg = DEFAULTS.copy()
    cfg.update(config)
    cfg["pass_split_null_byte"] = cfg["pass_split_null_byte"].lower() == "true"
    cfg["add_empty_pass"] = cfg["add_empty_pass"].lower() == "true"
    cfg["ssl_check"] = cfg["ssl_check"].lower() == "true"
    try:
        cfg["timeout"] = int(cfg["timeout"])
    except Exception as e:
        radlog(L_ERR, f"Error parsing timeout setting: {config['timeout']}")
        return None

    # Validate URL
    if not _validate_url(cfg["url"], cfg["ssl_check"]):
        radlog(L_ERR, f"Error parsing url setting: {config['url']}")
        return None

    # Log SSL verification status
    if not cfg["ssl_check"]:
        radlog(
            L_INFO,
            "SSL certificate verification is DISABLED.",
        )
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    return cfg


def _parse_request_attributes(auth_data: Tuple) -> Dict[str, Any]:
    """Parse request attributes from tuple format to dict.

    :param auth_data: The tuple containing the request from FreeRADIUS. It has
        the format: `(('User-Name', '"user1"'), ('User-Password', '"user1"'))`.
    :return: The same data but as dictionary, each tuple being a key-value pair.
    """
    request = {}
    for attr in auth_data:
        if len(attr) == 2:
            key, value = attr
            # Remove quotes if present (FreeRADIUS 3.x adds quotes around string values)
            if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            request[key] = value
    return request


def _build_reply(reply_items: Dict[str, Any]) -> Tuple:
    """Build reply_items tuple from dict, as the communication between
    rlm_python3 and this script only happens via tuples.

    :param reply_items: The dictionary to send as a reply.
    :return: The same dictionary formatted as a tuple for rlm_python3.
    """
    reply = []
    for key, value in reply_items.items():
        if isinstance(value, list):
            for v in value:
                reply.append((key, v))
        else:
            reply.append((key, value))
    return tuple(reply)


def _validate_state(hex_state: str) -> Optional[str]:
    """Validate and decode a hex-encoded State attribute.

    :param hex_state: Hex-encoded state string, optionally with '0x' prefix
    :return: Decoded state string, or None if invalid.
    """
    try:
        if not hex_state:
            return None

        if len(hex_state) > MAX_STATE_LENGTH:
            radlog(
                L_ERR,
                f"State attribute too long ({len(hex_state)} bytes, max {MAX_STATE_LENGTH})",
            )
            return None

        # Remove '0x' prefix if present
        if hex_state.startswith("0x"):
            hex_state = hex_state[2:]

        # Validate that the string contains only hex characters
        if not re.match(r"^[0-9a-fA-F]*$", hex_state):
            radlog(L_ERR, f"Invalid hex string in State: {hex_state}")
            return None

        # Decode from hex
        decoded = bytes.fromhex(hex_state).decode("latin-1")
        return decoded
    except (ValueError, UnicodeDecodeError) as e:
        radlog(L_ERR, f"Failed to decode State: {e}")
        return None


def _create_params_from_request(request: dict) -> Optional[dict]:
    """Takes a request object as created by _parse_request_attributes and
    return a dict object to send to eduMFA.

    :param request: The request object from _parse_request_attributes.
    :return: A dictionary to send to eduMFA, or None if it fails.
    """
    params: Dict[str, str] = {}

    if "State" in request:
        hex_state = request["State"]
        decoded_state = _validate_state(hex_state)
        if decoded_state is None:
            radlog(L_ERR, f"Client sent invalid State attribute: {str(hex_state)}")
            return None
        params["state"] = decoded_state

    if "Stripped-User-Name" in request:
        stripped_username = request["Stripped-User-Name"]
        if len(stripped_username) > MAX_USERNAME_LENGTH:
            radlog(
                L_ERR,
                f"Client sent invalid username: length is {len(stripped_username)}, but max is {MAX_USERNAME_LENGTH})",
            )
            return none
        params["user"] = stripped_username
    elif "User-Name" in request:
        username = request["User-Name"]
        if len(username) > MAX_USERNAME_LENGTH:
            radlog(
                L_ERR,
                f"Client sent invalid stripped username: length is {len(username)}, but max is {MAX_USERNAME_LENGTH}",
            )
            return None
        params["user"] = username

    if "User-Password" in request:
        password = request["User-Password"]
        if len(password) > MAX_PASSWORD_LENGTH:
            radlog(
                L_ERR,
                f"Client sent invalid password: length is {len(password)}, but max is {MAX_PASSWORD_LENGTH}",
            )
            return None
        if config["pass_split_null_byte"]:
            # Split on null byte and use first part (for compatibility with certain clients)
            parts = password.split("\x00")
            password = parts[0]
            if len(parts) > 1:
                radlog(
                    L_INFO,
                    f"Password contained null byte and was truncated to first part.",
                )
        params["pass"] = password
    elif config["add_empty_pass"]:
        params["pass"] = ""

    clientattribute = config["clientattribute"]
    if clientattribute and clientattribute in request:
        params["client"] = request[clientattribute]
    elif "NAS-IP-Address" in request:
        params["client"] = request["NAS-IP-Address"]
    elif "Packet-Src-IP-Address" in request:
        params["client"] = request["Packet-Src-IP-Address"]

    if config["realm"]:
        params["realm"] = realm
    elif "Realm" in request:
        params["realm"] = request["Realm"]

    if "NAS-Identifier" in request:
        params["RADIUS-NAS-Identifier"] = request["NAS-Identifier"]
    return params


def authenticate(auth_data: Tuple) -> Tuple[int, Tuple, Tuple]:
    """Handle authentication.

    :param auth_data: Tuple of request attributes
    :return: Tuple of (return_code, reply_tuple, config_tuple)
    """  # Load configuration if not already loaded
    if config is None:
        radlog(L_ERR, "Config was not loaded successfully, can't continue.")
        reply_items = {"Reply-Message": "Configuration error"}
        return (ReturnCode.RLM_MODULE_FAIL.value, _build_reply(reply_items), ())

    # Parse request attributes
    request = _parse_request_attributes(auth_data)

    radlog(L_DBG, f"New request with attributes: {_censor(request)}")

    params = _create_params_from_request(request)
    if not params:
        reply_items = {"Reply-Message": "Bad Request"}
        return (ReturnCode.RLM_MODULE_INVALID.value, _build_reply(reply_items), ())

    radlog(L_DBG, f"Sending request to eduMFA with: {_censor(params)}")

    # Forward request to eduMFA
    try:
        response = requests.post(
            config["url"],
            json=params,
            headers={"User-Agent": "FreeRADIUS"},
            timeout=config["timeout"],
            verify=config["ssl_check"],
        )
        content = response.text
    except Exception as e:
        radlog(L_ERR, f"eduMFA request failed: {e}")
        reply_items = {"Reply-Message": f"eduMFA request failed."}
        return (ReturnCode.RLM_MODULE_FAIL.value, _build_reply(reply_items), ())

    radlog(L_DBG, f"eduMFA response took: {response.elapsed.total_seconds()}s")
    radlog(L_DBG, f"eduMFA response: {content}")

    reply_items = {"Reply-Message": "Authentication failed"}
    g_return = ReturnCode.RLM_MODULE_REJECT

    try:
        decoded = json.loads(content)
        result = _get_or_dict(decoded, "result")
        detail = _get_or_dict(decoded, "detail")
        status = result.get("status")
        authentication_result = result.get("authentication")
        transaction_id = detail.get("transaction_id")
        message = detail.get("message", "")
        error_code = _get_or_dict(result, "error").get("code")

        if status is False:
            reply_items["Reply-Message"] = message
            # 904 is the error code for the user not being found by eduMFA.
            if error_code == 904:
                g_return = ReturnCode.RLM_MODULE_NOTFOUND
            else:
                radlog(L_ERR, f"eduMFA response indicates failure: {message}")
                g_return = ReturnCode.RLM_MODULE_FAIL
        elif authentication_result == "ACCEPT":
            reply_items["Reply-Message"] = "Authentication succeeded"
            g_return = ReturnCode.RLM_MODULE_OK
        elif authentication_result == "CHALLENGE":
            reply_items["Reply-Message"] = message
            reply_items["State"] = decoded["detail"]["transaction_id"]
            g_return = ReturnCode.RLM_MODULE_HANDLED
        elif authentication_result == "REJECT":
            reply_items["Reply-Message"] = message
            g_return = ReturnCode.RLM_MODULE_REJECT
        else:
            g_return = ReturnCode.RLM_MODULE_FAIL
            radlog(
                L_ERR,
                f"Unknown eduMFA response, please consider reporting this via the issue tracker. Response: '{decoded}'.",
            )
    except json.JSONDecodeError as e:
        radlog(
            L_ERR,
            f"Failed to parse JSON response from eduMFA: {e}. Response: {content}",
        )
    except Exception as e:
        radlog(
            L_ERR, f"Unexpected error parsing eduMFA response: {e}. Response: {content}"
        )

    # Avoid having the dockerprobe spam the RADIUS logs.
    # TODO test this with IPv6
    if params.get('user') != "_dockerprobe" and request["Packet-Src-IP-Address"] == "127.0.0.1":
        radlog(
            L_INFO,
            f"'{params.get('user')}' in realm '{params.get('realm')}' received authentication result: {g_return.name}.",
        )
    return (g_return.value, _build_reply(reply_items), ())


def instantiate(p) -> int:
    """Instantiate this module.

    :param p: A variable passed by rlm_python3, which is unneeded and is
        normally None anyway.
    :return: OK if the config was parsed successfully, else FAIL.
    """
    cfg = _load_config(radiusd.config)
    if cfg is None:
        radlog(L_ERR, "Failed to load configuration during instantiation")
        return ReturnCode.RLM_MODULE_FAIL.value
    else:
        global config
        config = cfg
        radlog(L_INFO, "Configuration was loaded successfully.")
        return ReturnCode.RLM_MODULE_OK.value


# Test the modules
if __name__ == "__main__":
    instantiate(None)
    print(authenticate((("User-Name", '"user1"'), ("User-Password", '"user1"'))))
