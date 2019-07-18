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

import click


@click.command()
@click.option('-n', '--number_proxies',
              default=1,
              type=int,
              help='Number of proxies to execute')
@click.option('-p', '--proxy',
              required=True,
              type=str,
              nargs=2,
              multiple=True)
def main():
    pass


if __name__ == '__main__':
    main()
