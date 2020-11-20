from gevent.monkey import patch_all  # isort:skip

patch_all()  # isort:skip

import hashlib
import signal
from functools import partial
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import click
import gevent
import gevent.signal
from gevent.event import Event
from structlog import get_logger

import raiden.log_config
from raiden.constants import DISCOVERY_DEFAULT_ROOM
from raiden.network.transport.matrix.utils import (
    UserPresence,
    join_broadcast_room,
    login,
    make_client,
    make_room_alias,
)
from raiden.utils.signer import LocalSigner, Signer
from raiden_contracts.constants import CHAINNAME_TO_ID


log = get_logger(__name__)


def log_presence(server: str, event: Dict[str, Any], update_id: int) -> None:
    log.info(
        "Presence update",
        server=server,
        user_id=event["sender"],
        presence=UserPresence(event["content"]["presence"]),
        update_id=update_id,
    )


def monitor_server_presence(
    server: str, signer: Signer, network_names: List[str], stop_event: Event
):
    server_name = urlparse(server).netloc
    client = make_client(lambda x: False, lambda x: None, [server])
    login(client=client, signer=signer)
    client.add_presence_listener(partial(log_presence, server))
    client.start_listener_thread(30_000, 1_000)
    for network_name in network_names:
        discovery_room_alias = make_room_alias(
            CHAINNAME_TO_ID[network_name], DISCOVERY_DEFAULT_ROOM
        )

        discovery_room = join_broadcast_room(client, f"#{discovery_room_alias}:{server_name}")
    log.info("Monitoring started", server=server)
    stop_event.wait()
    client.stop()


@click.command()
@click.option("-s", "--server", "servers", multiple=True, required=True)
@click.option(
    "-n",
    "--network",
    "networks",
    multiple=True,
    required=True,
    type=click.Choice(CHAINNAME_TO_ID.keys()),
)
@click.option("-p", "--privkey-seed", required=True)
@click.option("--log-file", type=click.Path(dir_okay=False, file_okay=True))
def main(
    servers: List[str], networks: List[str], privkey_seed: str, log_file: Optional[str]
) -> None:
    if log_file:
        # Increase log rotation count
        raiden.log_config.LOG_BACKUP_COUNT = 50
        raiden.log_config.configure_logging(
            {"": "INFO", "raiden": "DEBUG", "__main__": "DEBUG"},
            log_json=True,
            debug_log_file_path=log_file,
        )
    else:
        raiden.log_config.configure_logging(
            {"": "INFO", "raiden": "DEBUG", "__main__": "DEBUG"},
            log_json=True,
            disable_debug_logfile=True,
        )
    stop_event = Event()

    def stop():
        log.info("Stopping")
        stop_event.set()

    gevent.signal.signal(signal.SIGQUIT, stop)
    gevent.signal.signal(signal.SIGTERM, stop)
    gevent.signal.signal(signal.SIGINT, stop)

    signer = LocalSigner(hashlib.sha256(privkey_seed.encode()).digest())
    log.info("Using address", address=signer.address_hex)

    monitors = {
        gevent.spawn(monitor_server_presence, server, signer, networks, stop_event)
        for server in servers
    }
    stop_event.wait()
    gevent.joinall(monitors)


if __name__ == "__main__":
    main()
