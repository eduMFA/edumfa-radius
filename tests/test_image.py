# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 DAASI International GmbH <info@daasi.de>

import base64
import json
import re
from os import getenv
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

EDUMFA_TAG = "2.9.5@sha256:fe9867f6a7fa7e2269c44305c7954d3ae35765bd54bcc6fdac7294f2881ceac7"
POSTGRES_TAG = "17-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73"
OTPKEY = "3132333435363738393031323334353637383930"
VALID_OTP_VALUES = [
    "755224",
    "287082",
    "359152",
    "969429",
    "338314",
    "254676",
    "287922",
    "162583",
    "399871",
    "520489",
]
DB_CONTAINER_NAME = "edumfa-radius-test-postgres"
TEST_DATA_DIR = Path(__file__).parent / "test_data"

postgres = PostgresContainer(f"postgres:{POSTGRES_TAG}", name=DB_CONTAINER_NAME)
edumfa = DockerContainer(f"ghcr.io/edumfa/edumfa:{EDUMFA_TAG}")

radius_image = None
radius_image_tag = getenv("EDUMFA_RADIUS_TEST_IMAGE")
if not radius_image_tag:
    radius_image = DockerImage(path=".").build()
    radius_image_tag = str(radius_image)
radius = DockerContainer(radius_image_tag)


def bashify_command(cmd: str) -> str:
    """Encode a command in base64 and create a bash command to decode and execute it.

    This is used to work around nesting levels of commands that would otherwise
    be unreadable. Yes, this is an ugly hack.

    :param cmd: The command to base64 encode.
    :return: The bash command to execute the cmd.
    """
    cmd_b64 = base64.b64encode(cmd.encode("utf-8")).decode()
    return f'bash -c "echo -n {cmd_b64} | base64 -d | bash -s"'


def try_stop_containers():
    """Try to stop containers to avoid them lingering on e.g. failure."""
    containers = (radius, edumfa, postgres)
    for container in containers:
        try:
            container.stop()
        except:
            pass


@pytest.fixture(scope="module", autouse=True)
def remove_built_image(request):
    def _remove_built_image() -> None:
        if not getenv("EDUMFA_RADIUS_TEST_IMAGE"):
            radius_image.remove()
        try_stop_containers()

    request.addfinalizer(_remove_built_image)


def _setup_with_network(request, network):
    """Helper function for function setup which enables readable try-excepting.

    :param request: The pytest request for the test function.
    :param network: The testcontainers network to use for the containers.
    """
    # Network setup
    network.create()
    postgres.with_network(network)
    edumfa.with_network(network)
    radius.with_network(network)

    # Postgres setup
    postgres.waiting_for(
        LogMessageWaitStrategy(r".*database system is ready to accept connections")
    )
    postgres.start()

    # eduMFA setup
    edumfa.with_name("edumfa")
    edumfa_env = {
        "DB_DATABASE": postgres.dbname,
        "DB_DRIVER": "postgresql+psycopg2",
        "DB_HOSTNAME": f"{DB_CONTAINER_NAME}:5432",
        "DB_PASSWORD": postgres.password,
        "DB_USER": postgres.username,
        "EDUMFA_PEPPER": "46685d2555dc23910921cca2a4f2de0a2d021405fd5461b4",
        "SECRET_KEY": "8a155906a8a8d30ccf2980099faaa3e904f5b8bb75862c73",
    }
    edumfa.with_envs(**edumfa_env)
    edumfa.waiting_for(LogMessageWaitStrategy(r".*Listening at: http://0.0.0.0:8000.*"))
    edumfa.start()

    # Add resolver and realm
    edumfa.exec("edumfa-manage -q resolver create_internal testresolver")
    edumfa.exec("edumfa-manage -q realm create testrealm testresolver")
    # add user1 to testresolver
    add_user_cmd = 'echo \'from edumfa.lib.user import create_user; create_user("testresolver", {"username":"user1","email":"user1@user1.local"}, password="user1")\' | edumfa-manage shell'
    add_user_cmd = bashify_command(add_user_cmd)
    edumfa.exec(add_user_cmd)
    # give a token with OTPKEY to user1
    add_token_cmd = f'echo \'from edumfa.lib.user import User; from edumfa.lib.token import init_token; user = User("user1",realm="testrealm"); init_token({{"type": "hotp","otpkey": "{OTPKEY}"}}, user=user)\' | edumfa-manage shell'
    add_token_cmd = bashify_command(add_token_cmd)
    edumfa.exec(add_token_cmd)
    # set policy for Challenge-Response
    add_policy_cmd = 'echo \'from edumfa.lib.policy import set_policy;set_policy(name="chap2",scope="authentication",action={"challenge_response": "hotp", "otppin": "userstore"})\' | edumfa-manage shell'
    add_policy_cmd = bashify_command(add_policy_cmd)
    edumfa.exec(add_policy_cmd)

    # RADIUS setup
    radius.with_name("edumfa-radius")
    radius_env = {"RADIUS_DEBUG": "true"}
    radius.with_envs(**radius_env)
    radius.with_volume_mapping(
        str(TEST_DATA_DIR / "clients.conf"), "/etc/freeradius/3.0/clients.conf"
    )
    radius.with_volume_mapping(
        str(TEST_DATA_DIR / "mod_config.unlang"),
        "/etc/freeradius/3.0/mods-available/edumfa",
    )
    radius.waiting_for(LogMessageWaitStrategy(r".*Ready to process requests"))
    radius.start()


@pytest.fixture(scope="function", autouse=True)
def setup(request):
    network = Network()

    def remove_objects() -> None:
        try_stop_containers()
        network.remove()

    try:
        _setup_with_network(request, network)
    except:
        remove_objects()
        raise
    request.addfinalizer(remove_objects)


def test_auth():
    # Make sure direct auth via eduMFA's API is working.
    response = edumfa.exec(
        f"curl -s 'http://localhost:8000/validate/check?user=user1&pass=user1{VALID_OTP_VALUES[0]}'"
    ).output
    response = json.loads(response)
    assert response["result"]["authentication"] == "ACCEPT"

    # Make sure the RADIUS container works.
    check_cmd = f"echo 'User-Name=user1,User-Password=user1{VALID_OTP_VALUES[1]}' | radclient -r 1  localhost:1812 auth testing123"
    check_cmd = bashify_command(check_cmd)
    response = radius.exec(check_cmd).output
    assert "Received Access-Accept" in str(response)

    check_cmd = f"echo 'User-Name=user1,User-Password=user1' | radclient -x -r 1  localhost:1812 auth testing123"
    check_cmd = bashify_command(check_cmd)
    response = radius.exec(check_cmd).output
    assert "Received Access-Challenge" in str(response)

    # extract state
    state = re.search(r"State = (\w*)", response.decode())[1]
    assert state.startswith("0x")
    check_cmd = f"echo 'User-Name=user1,User-Password={VALID_OTP_VALUES[2]},State={state}' | radclient -r 1  localhost:1812 auth testing123"
    check_cmd = bashify_command(check_cmd)
    response = radius.exec(check_cmd).output
    assert "Received Access-Accept" in str(response)
