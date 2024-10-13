#!/usr/bin/python3
# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2020 Frédéric Pierret <frederic.pierret@qubes-os.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import argparse
import json
import os
import requests
import sys

from component import Component
from jinja2 import Template
from pathlib import Path
from typing import Optional


class ReportBuilder:
    MAXIMUM_PAGINATION = 20

    def __init__(self, gitlab_url: str, current_release: str, next_release: str, gitlab_token: Optional[str] = None):
        self._current_release = current_release
        self._gitlab_token = gitlab_token
        self._gitlab_url = gitlab_url
        self._next_release = next_release

        with open('gitlab_query_pipeline.j2', 'r') as f:
            self._gitlab_query_pipeline_template = Template(f.read())

        with open('gitlab_query.j2', 'r') as f:
            self._gitlab_query_template = Template(f.read())

        with open('template.md.j2', 'r') as template_fd:
            self._template_md = Template(template_fd.read())

        with open('template.html.j2', 'r') as template_fd:
            self._template_html = Template(template_fd.read())
    
    def _build_gitlab_query(self, pagination_offset):
        query_pipelines_stubs = [
            self._gitlab_query_pipeline_template.render(release_name="current", release_branch=f"release{self._current_release}"),
            self._gitlab_query_pipeline_template.render(release_name="next", release_branch=f"release{self._next_release}"),
            self._gitlab_query_pipeline_template.render(release_name="main", release_branch="main"),
        ]

        gitlab_query = self._gitlab_query_template.render(
            pipelines="\n".join(query_pipelines_stubs),
            pagination_offset=pagination_offset,
        )

        return gitlab_query
    
    def _error_and_exit(self, error_message: str):
        """Print an error message and exit program"""

        print(error_message, file=sys.stderr)
        raise RuntimeError

    def _get_components(self):
        projects = []
        pagination_offset = None
        for i in range(self.MAXIMUM_PAGINATION):
            data = self._query_pipelines(pagination_offset)
            projects += data['data']['group']['projects']['nodes']

            if not data['data']['group']['projects']['pageInfo']['hasNextPage']:
                break

            pagination_offset = data['data']['group']['projects']['pageInfo']['endCursor']

        components = [Component(component) for component in projects]
        return components
    
    def _get_distros(self, components):
        distros = {'current_release': {}, 'next_release': {}}

        for component in components:
            print(f"* Getting build status for component '{component.name}'")
            for i in range(2):
                if i == 0:
                    release_status = component.get_current_release_status(self._current_release)
                    release_distros = distros['current_release']
                else:
                    release_status = component.get_next_release_status(self._next_release)
                    release_distros = distros['next_release']
            
                if release_status:
                    for distro_name, status in release_status.items():
                        release_distros.setdefault(distro_name, {})
                        release_distros[distro_name][component.short_name] = status
        return distros

    def _query_pipelines(self, pagination_offset=None):
        gitlab_query = self._build_gitlab_query(pagination_offset)

        headers = { "Content-Type": "application/json", }

        if self._gitlab_token is not None:
            headers["Authorization"] = f"Bearer {self._gitlab_token}"

        r = requests.post('https://gitlab.com/api/graphql',
                        headers=headers,
                        json={"query": gitlab_query})
        if not r.ok:
            self._error_and_exit(r.text)

        raw_data = r.json()

        if 'errors' in raw_data:
            self._error_and_exit(raw_data['errors'])

        return raw_data


    @staticmethod
    def _pipeline_status_to_string(status):
        if status in ('created', 'waiting_for_resource', 'preparing', 'pending',
                    'running', 'manual', 'scheduled'):
            return 'unknown'

        if status in ('failed', 'canceled', 'skipped'):
            return 'failure'

        if status in ('success', 'passed'):
            return 'success'


    def generate_report(self):
        print("* Getting components...")
        components = self._get_components()
        distros = self._get_distros(components)

        # Flatten for HTML display
        qubes_status = {}
        for release in ['current_release', 'next_release']:
            for distro, components in distros[release].items():
                qubes_status.setdefault(distro, {})
                for component_name, component_status in components.items():
                    qubes_status[distro].setdefault(component_name, {})
                    qubes_status[distro][component_name][release] = {}
                    for stage in ["build", "install", "repro"]:
                        job = component_status.get(stage)
                        if job:
                            qubes_status[distro][component_name][release][stage] = {
                                "url": f"{self._gitlab_url}{job['detailsPath']}",
                                "badge": "{}_{}.svg".format(stage, self._pipeline_status_to_string(job['text'])),
                                "text": f"{stage.capitalize()} Status"
                            }

        qubes_status = dict(sorted(qubes_status.items()))

        with open('public/index.md', 'w') as fd:
            fd.write(self._template_md.render(
                current_release=self._current_release,
                next_release=self._next_release,
                qubes_status=qubes_status))

        with open('public/index.html', 'w') as fd:
            fd.write(self._template_html.render(current_release=self._current_release,
                next_release=self._next_release,
                qubes_status=qubes_status))


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--gitlab", default="https://gitlab.com", help="Gitlab instance URL")
        parser.add_argument("--current-release",required=True, help="Current QubesOS release number")
        parser.add_argument("--next-release", required=True, help="Next QubesOS release number")
        args = parser.parse_args()

        gitlab_token = os.environ.get('GITLAB_API_TOKEN')
        if gitlab_token is None:
            gitlab_token_file = Path('~/.gitlab-token').expanduser()
            if gitlab_token_file.is_file():
                gitlab_token = gitlab_token_file.read_text().strip()

        builder = ReportBuilder(args.gitlab, args.current_release, args.next_release, gitlab_token).generate_report()
    except RuntimeError:
        sys.exit(1)
