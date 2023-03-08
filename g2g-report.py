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

parser = argparse.ArgumentParser()

parser.add_argument('--dist', action='store', required=False, default=None,
                    nargs='+', help='Dist to process')
parser.add_argument('--components', action='store', required=False,
                    nargs='+', help='Components to process')
parser.add_argument('--gitlab', action='store', required=False,
                    help='Gitlab instance URL',
                    default="https://gitlab.com")
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--debug', action='store_true')

query = """
query {
  group(fullPath: "QubesOS") {
    projects {
      nodes {
        name
        release41: pipelines(ref: "release4.1", first: 1) {
          nodes {
            id
            jobs {
              nodes {
                name
                detailedStatus {
                  detailsPath
                  text
                }
              }
            }
            status
          }
        }
        main: pipelines(ref: "main", first: 1) {
          nodes {
            id
            jobs {
              nodes {
                name
                detailedStatus {
                  detailsPath
                  text
                }
              }
            }
            status
          }
        }
      }
    }
  }
}
"""


def query_pipelines(token):
    headers={
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    r = requests.post('https://gitlab.com/api/graphql',
                      headers=headers,
                      json={"query": query})
    if not r.ok:
        print(r.text)
        return
    raw_data = r.json()
    if 'errors' in raw_data:
        print(raw_data['errors'])
        return
    projects = raw_data['data']['group']['projects']['nodes']
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


def pipeline_status(status):
    if status in ('created', 'waiting_for_resource', 'preparing', 'pending',
                  'running', 'manual', 'scheduled'):
        return 'unknown'

    if status in ('failed', 'canceled', 'skipped'):
        return 'failure'

    if status in ('success', 'passed'):
        return 'success'


def main(args=None):
    args = parser.parse_args(args)
    token = None
    if os.environ.get('GITLAB_API_TOKEN', None):
        token = os.environ['GITLAB_API_TOKEN']
    elif os.path.exists(os.path.expanduser('~/.gitlab-token')):
        with open(os.path.expanduser('~/.gitlab-token')) as f:
            token = f.read().strip()

    data = query_pipelines(token)

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
    sys.exit(main())
