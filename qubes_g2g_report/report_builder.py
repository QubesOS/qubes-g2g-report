#!/usr/bin/python3
# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2024 Guillaume Chinal <guiiix@invisiblethingslab.com>
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


import requests
import sys


from babel.dates import format_timedelta, format_datetime
from datetime import datetime, timezone
from qubes_g2g_report.component import Component
from jinja2 import Template
from typing import Optional

from qubes_g2g_report.enums.job_type import JobType


class ReportBuilder:
    MAXIMUM_PAGINATION = 20

    def __init__(self, gitlab_url: str, current_release: str, next_release: str, gitlab_token: Optional[str] = None):
        self._current_release = current_release
        self._gitlab_token = gitlab_token
        self._gitlab_url = gitlab_url
        self._next_release = next_release

        with open('templates/gitlab_query_pipeline.j2', 'r') as f:
            self._gitlab_query_pipeline_template = Template(f.read())

        with open('templates/gitlab_query.j2', 'r') as f:
            self._gitlab_query_template = Template(f.read())

        with open('templates/template.md.j2', 'r') as template_fd:
            self._template_md = Template(template_fd.read())

        with open('templates/template.html.j2', 'r') as template_fd:
            self._template_html = Template(template_fd.read())

    def _build_gitlab_query(self, pagination_offset):
        query_pipelines_stubs = [
            self._gitlab_query_pipeline_template.render(release_name="current",
                                                        release_branch=f"release{self._current_release}"),
            self._gitlab_query_pipeline_template.render(release_name="next",
                                                        release_branch=f"release{self._next_release}"),
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
            print(f"* Getting build jobs for component '{component.name}'")
            for i in range(2):
                if i == 0:
                    release_status = component.get_current_release_jobs(self._current_release)
                    release_distros = distros['current_release']
                else:
                    release_status = component.get_next_release_jobs(self._next_release)
                    release_distros = distros['next_release']

                if release_status:
                    for distro_name, jobs in release_status.items():
                        release_distros.setdefault(distro_name, {})
                        release_distros[distro_name][component.short_name] = {
                            'jobs': jobs,
                            'component': component,
                        }
        return distros

    def _query_pipelines(self, pagination_offset=None):
        gitlab_query = self._build_gitlab_query(pagination_offset)

        headers = {"Content-Type": "application/json", }

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

    def generate_report(self):
        print("* Getting components...")
        components = self._get_components()
        distros = self._get_distros(components)
        current_time = datetime.now(timezone.utc)

        # Flatten for HTML display
        qubes_status = {}
        for release in ['current_release', 'next_release']:
            for distro, components in distros[release].items():
                qubes_status.setdefault(distro, {})
                for component_name, component_details in components.items():
                    component = component_details['component']
                    component_release_jobs = component_details['jobs']

                    qubes_status[distro].setdefault(component_name, {})
                    qubes_status[distro][component_name][release] = {}
                    qubes_status[distro][component_name]['project_url'] = f"{self._gitlab_url}/QubesOS/{component.name}"

                    qubes_status[distro][component_name][release]["last_job_creation_time"] = ""
                    qubes_status[distro][component_name][release]["last_job_time_delta"] = ""
                    for stage in [JobType.BUILD, JobType.INSTALL, JobType.REPRO]:
                        job = component_release_jobs.get(stage)
                        if job:
                            qubes_status[distro][component_name][release]["last_job_creation_time"] = format_datetime(job.creation_time, locale="en")
                            qubes_status[distro][component_name][release]["last_job_time_delta"] = format_timedelta(job.creation_time - current_time, add_direction=True, locale="en")
                            qubes_status[distro][component_name][release][stage.name.lower()] = {
                                "url": f"{self._gitlab_url}{job.path}",
                                "badge": "{}_{}.svg".format(stage.name.lower(), job.status.name.lower()),
                                "text": f"{job.type.name.capitalize()} Status",
                            }


        qubes_status = dict(sorted(qubes_status.items()))
        for distro in qubes_status.keys():
            qubes_status[distro] = dict(sorted(qubes_status[distro].items()))

        with open('public/index.md', 'w') as fd:
            fd.write(self._template_md.render(
                current_release=self._current_release,
                next_release=self._next_release,
                qubes_status=qubes_status))

        with open('public/index.html', 'w') as fd:
            fd.write(self._template_html.render(current_release=self._current_release,
                                                next_release=self._next_release,
                                                qubes_status=qubes_status))