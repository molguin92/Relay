#!/usr/bin/env python
#  Copyright 2019 Manuel Olguín Muñoz <manuel@olguin.se><molguin@kth.se>
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import enum
import ipaddress
import logging
import signal
from functools import partial
from inspect import Parameter, signature
from threading import Event
from typing import Dict, List, Optional, Tuple

import click
import logzero
import toml

from defaults import RelayDefaults
from distributions import Distribution
from relay import DuplexRelay

avail_distributions = {cls.__name__.upper(): cls for cls in
                       Distribution.__subclasses__()}


class State:
    def __init__(self):
        self.verbosity = -1
        self.relay = None

    def set_relay(self, relay: DuplexRelay):
        self.relay = relay

    def set_verbosity(self, value):
        if value >= self.verbosity:
            self.verbosity = value
            if value == 1:
                logzero.setup_default_logger(level=logging.WARNING)
            elif value == 2:
                logzero.setup_default_logger(level=logging.INFO)
            elif value >= 3:
                logzero.setup_default_logger(level=logging.DEBUG)
            else:
                logzero.setup_default_logger(level=logging.ERROR)


pass_state = click.make_pass_decorator(State, ensure=True)


def add_verbosity_option(fn):
    def __set_verbosity(ctx, param, value):
        state = ctx.ensure_object(State)
        state.set_verbosity(value)
        return state

    fn = click.option('-v', help='Set verbosity',
                      count=True, expose_value=False,
                      callback=__set_verbosity,
                      type=int, default=0)(fn)
    return fn


def parse_IP_address(address: str) -> Tuple[str, int]:
    try:
        [ip, port] = address.split(':')
        ipaddress.ip_address(ip)
        port = int(port)
        assert port <= 65535
        return ip, port
    except:
        raise RuntimeError(f'Could not parse {address} into a valid IP address')


class TOMLConfig(click.File):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def convert(self, value, param, ctx):
        try:
            return toml.load(super().convert(value, param, ctx))
        except Exception as e:
            self.fail(f'{value} is not a valid TOML configuration file. '
                      f'Exception when parsing: {e}',
                      param, ctx)


class INetAddress(click.ParamType):
    class TYPE(enum.IntEnum):
        TO = 0
        FROM = 1

    def __init__(self, to_or_from: Optional[TYPE] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = {
            INetAddress.TYPE.TO  : 'HOST_ADDRESS:HOST_PORT',
            INetAddress.TYPE.FROM: 'BIND_ADDRESS:BIND_PORT'
        }.get(to_or_from, 'ADDRESS:PORT')

    def convert(self, value, param, ctx):
        try:
            ip, port = parse_IP_address(value)
        except RuntimeError as e:
            self.fail(str(e), param, ctx)

        return ip, port


@click.group()
@pass_state
@add_verbosity_option
def cli(_):
    pass


@cli.group(help='Start a single proxy from the CLI.')
@pass_state
@click.option('-c', '--chunk_size', type=int, default=RelayDefaults.CHUNK_SIZE,
              required=False, show_default=True,
              help='Read/write chunk size for the TCP proxy in bytes.')
@click.argument('bind_addr', type=INetAddress(INetAddress.TYPE.FROM))
@click.argument('connect_addr', type=INetAddress(INetAddress.TYPE.TO))
@add_verbosity_option
def proxy(state, chunk_size, bind_addr, connect_addr):
    lhost, lport = bind_addr
    chost, cport = connect_addr
    state.set_relay(DuplexRelay(
        listen_host=lhost,
        listen_port=lport,
        connect_host=chost,
        connect_port=cport,
        chunk_size=chunk_size
    ))


@pass_state
def single_run_proxy_callback(state, dist_class, *args, **kwargs):
    state.relay.set_distribution(dist_class(*args, **kwargs))

    def __sig_handler(*args, **kwargs):
        state.relay.stop()

    signal.signal(signal.SIGINT, __sig_handler)
    state.relay.start()  # waits until end

    state.relay.join()


# dynamically add distributions as commands
for dist_name, dist in avail_distributions.items():
    sig = signature(dist)
    params = dict(sig.parameters)

    args = [
        click.Option(param_decls=(f'--{name}',),
                     required=(param.default == Parameter.empty),
                     default=(param.default
                              if param.default != Parameter.empty
                              else None),
                     show_default=True,
                     nargs=1,
                     type=param.annotation)
        for name, param in params.items()
    ]

    cmd = click.Command(dist_name.lower(),
                        callback=partial(single_run_proxy_callback,
                                         dist_class=dist),
                        params=args)
    proxy.add_command(add_verbosity_option(cmd))


@cli.command()
@pass_state
@add_verbosity_option
@click.argument('config', type=TOMLConfig())
def from_file(_, config: Dict):
    proxies: List[DuplexRelay] = list()
    for p_config in config['proxies']:
        baddr, bport = parse_IP_address(p_config['bind_addr'])
        caddr, cport = parse_IP_address(p_config['connect_addr'])
        chunk_size = p_config.get('chunk_size', 4096)  # todo: defaults

        dist_name = p_config['distribution']['name'].upper()
        dist_params = p_config['distribution']['params']

        dist = avail_distributions[dist_name](**dist_params)

        proxies.append(DuplexRelay(
            listen_host=baddr, listen_port=bport,
            connect_host=caddr, connect_port=cport,
            chunk_size=chunk_size,
            delay_dist=dist
        ))

    def __sig_handler(*args, **kwargs):
        for p in proxies:
            p.stop()
        exit(0)

    signal.signal(signal.SIGINT, __sig_handler)

    for p in proxies:
        p.start()

    Event().wait()  # wait forever


if __name__ == '__main__':
    cli()
