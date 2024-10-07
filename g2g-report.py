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

import os
import argparse
import sys
import json
import requests

from jinja2 import Template
from pathlib import Path


class ReportBuilder:
    def __init__(self, gitlab_url: str, current_release: str, next_release: str, gitlab_token: str):
        self._current_release = current_release
        self._gitlab_token = gitlab_token
        self._gitlab_url = gitlab_url
        self._next_release = next_release

        with open('gitlab_query_pipeline.j2', 'r') as f:
            self._gitlab_query_pipeline_template = Template(f.read())

        with open('gitlab_query.j2', 'r') as f:
            self._gitlab_query_template = Template(f.read())

    def error_and_exit(self, error_message: str):
        """Print an error message and exit program"""

        print(error_message, file=sys.stderr)
        raise RuntimeError


    def get_pipelines_data(self, token: str):
        projects = query_pipelines(token)['data']['group']['projects']['nodes']
        data = {}
        for proj in projects:
            name = proj['name'][6:]
            data[name] = {}
            pipeline_41 = proj['release41']['nodes']
            if pipeline_41:
                job_41 = pipeline_41[0]['jobs']['nodes']
                data[name]['4.1'] = job_41

            pipeline_42 = proj['main']['nodes']
            if pipeline_42:
                jobs_42 = pipeline_42[0]['jobs']['nodes']
                data[name]['4.2'] = jobs_42
        return data


    def query_pipelines(token: str):
        headers = {
            "Content-Type": "application/json",
        }

        if token:
            headers["Authorization"] = f"Bearer {token}"

        r = requests.post('https://gitlab.com/api/graphql',
                        headers=headers,
                        json={"query": query})
        if not r.ok:
            error_and_exit(r.text)

        raw_data = r.json()

        if 'errors' in raw_data:
            error_and_exit(raw_data['errors'])

        return raw_data


    def pipeline_status(status):
        if status in ('created', 'waiting_for_resource', 'preparing', 'pending',
                    'running', 'manual', 'scheduled'):
            return 'unknown'

        if status in ('failed', 'canceled', 'skipped'):
            return 'failure'

        if status in ('success', 'passed'):
            return 'success'


    def generate_report(args=None):
        data = get_pipelines_data(token)

        # WIP: use distfile.json on Qubes repo
        with open('distfile.json') as fd:
            distfile_data = json.loads(fd.read())

        if args.dist:
            dists = args.dist
        else:
            dists = []
            for release in distfile_data["releases"].keys():
                dists += ["dom0-%s" % dist for dist in distfile_data["releases"][release]["dom0"]]
                dists += ["vm-%s" % dist for dist in distfile_data["releases"][release]["vm"]]

        dists = sorted(set(dists))
        qubes_status = {}
        for dist in dists:
            print("-> Generating report for %s..." % dist)
            qubes_status[dist] = {}
            for component in sorted(distfile_data["components"].keys()):
                # if args.components and component not in args.components:
                #     continue
                qubes_status[dist][component] = {}
                component_data = distfile_data["components"][component]["releases"]
                for release in component_data.keys():
                    branch = component_data[release].get("branch", None)
                    qubes_status[dist][component][release] = {}
                    if branch:
                        pipeline = data.get(component, {}).get(release, [])
                        if pipeline:
                            build_job = None
                            install_job = None
                            repro_job = None
                            for job in pipeline:
                                if job['name'] == "build:%s" % dist:
                                    build_job = job
                                elif job['name'] == "install:%s" % dist:
                                    install_job = job
                                elif job['name'] == "repro:%s" % dist:
                                    repro_job = job

                            if build_job:
                                qubes_status[dist][component][release]["build"] = {
                                    "url": args.gitlab + build_job['detailedStatus']['detailsPath'],
                                    "badge": "build_%s.svg" % pipeline_status(build_job['detailedStatus']['text']),
                                    "text": "Build Status"
                                }
                            if install_job:
                                qubes_status[dist][component][release]["install"] = {
                                    "url": args.gitlab + install_job['detailedStatus']['detailsPath'],
                                    "badge": "install_%s.svg" % pipeline_status(install_job['detailedStatus']['text']),
                                    "text": "Install Status"
                                }
                            if repro_job:
                                qubes_status[dist][component][release]["repro"] = {
                                    "url": args.gitlab + repro_job['detailedStatus']['detailsPath'],
                                    "badge": "repro_%s.svg" % pipeline_status(repro_job['detailedStatus']['text']),
                                    "text": "Repro Status"
                                }

                    # no need to display empty lines?
                    if not qubes_status[dist][component][release]:
                        del qubes_status[dist][component][release]

                # no need to display empty lines?
                if not qubes_status[dist][component]:
                    del qubes_status[dist][component]

        with open('template.md.jinja', 'r') as template_fd:
            template_md = Template(template_fd.read())

        with open('template.html.jinja', 'r') as template_fd:
            template_html = Template(template_fd.read())

        data = {"qubes_status": qubes_status}

        with open('public/index.md', 'w') as fd:
            fd.write(template_md.render(**data))

        with open('public/index.html', 'w') as fd:
            fd.write(template_html.render(**data))





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

        if gitlab_token is None:
            print("ERROR: Gitlab token not found. Please fill file ~/.gitlab_token or set GITLAB_API_TOKEN environment variable.", file=sys.stderr)
            exit(1)

        builder = ReportBuilder(args.gitlab, args.current_release, args.next_release, gitlab_token).generate_report()
    except RuntimeError:
        sys.exit(1)
