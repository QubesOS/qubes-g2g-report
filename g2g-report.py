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

from cli.gitlab import GitlabCli
from jinja2 import Template

parser = argparse.ArgumentParser()

parser.add_argument('--dist', action='store', required=True,
                    nargs='+', help='Dist to process')
parser.add_argument('--components', action='store', required=False,
                    nargs='+', help='Components to process')
parser.add_argument('--gitlab', action='store', required=False,
                    help='Gitlab instance URL',
                    default="https://gitlab.com")
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--debug', action='store_true')


def pipeline_status(status):
    if status in ('created', 'waiting_for_resource', 'preparing', 'pending',
                  'running', 'manual', 'scheduled'):
        return 'unknown'

    if status in ('failed', 'canceled', 'skipped'):
        return 'failure'

    if status == 'success':
        return status


def main(args=None):
    args = parser.parse_args(args)
    token = os.environ.get('GITLAB_API_TOKEN', None)
    cli = GitlabCli(args.gitlab, token)

    # WIP: use distfile.json on Qubes repo
    with open('distfile.json') as fd:
        distfile_data = json.loads(fd.read())

    # Get pipelines first
    for component in distfile_data["components"].keys():
        if args.components and component not in args.components:
            continue
        print("-> Fetching pipelines for %s..." % component)
        for release in distfile_data["components"][component][
                "releases"].keys():
            branch = distfile_data["components"][component]["releases"][
                release].get("branch", None)
            distfile_data["components"][component]["releases"][release][
                "pipeline"] = \
                cli.get_pipeline('QubesOS', 'qubes-' + component, branch,
                                 only_finished=True)

    qubes_status = {}
    for dist in args.dist:
        print("-> Generating report for %s..." % dist)
        qubes_status[dist] = {}
        for component in sorted(distfile_data["components"].keys()):
            if args.components and component not in args.components:
                continue
            qubes_status[dist][component] = {}
            for release in distfile_data["components"][component][
                    "releases"].keys():
                branch = distfile_data["components"][component]["releases"][
                    release].get("branch", None)
                qubes_status[dist][component][release] = {}
                if branch:
                    pipeline = \
                        distfile_data["components"][component]["releases"][
                            release]["pipeline"]
                    if pipeline:
                        build_job = None
                        install_job = None
                        repro_job = None
                        for job in pipeline.jobs.list():
                            if job.name == "build:%s" % dist:
                                build_job = job
                            elif job.name == "install:%s" % dist:
                                install_job = job
                            elif job.name == "repro:%s" % dist:
                                repro_job = job

                        if build_job:
                            qubes_status[dist][component][release]["build"] = {
                                "url": build_job.web_url,
                                "badge": "build_%s.svg" % pipeline_status(
                                    build_job.status),
                                "text": "Build Status"
                            }
                        if install_job:
                            qubes_status[dist][component][release][
                                "install"] = {
                                "url": install_job.web_url,
                                "badge": "install_%s.svg" % pipeline_status(
                                    install_job.status),
                                "text": "Install Status"
                            }
                        if repro_job:
                            qubes_status[dist][component][release]["repro"] = {
                                "url": repro_job.web_url,
                                "badge": "repro_%s.svg" % pipeline_status(
                                    repro_job.status),
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

    with open('public/qubes_status.md', 'w') as fd:
        fd.write(template_md.render(**data))

    with open('public/qubes_status.html', 'w') as fd:
        fd.write(template_html.render(**data))


if __name__ == '__main__':
    sys.exit(main())
