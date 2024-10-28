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


import re
import requests


from jinja2 import Template
from qubes_g2g_report.enums.job_type import JobType
from qubes_g2g_report.job import Job
from typing import Dict, List, Optional


class Component:
    def __init__(self, gitlab_project_node: dict):
        self._gitlab_project_node = gitlab_project_node

        with open('templates/gitlab_query_pipeline.j2', 'r') as f:
            self._gitlab_query_pipeline_template = Template(f.read())

        with open('templates/gitlab_query_project_pipeline.j2', 'r') as f:
            self._gitlab_query_project_pipeline_template = Template(f.read())

    def _get_pipeline_jobs(self, branch_node_name: str) -> Optional[List[Job]]:
        branch_pipeline_jobs = self._get_branch_pipeline_jobs(branch_node_name)
        if branch_pipeline_jobs is not None:
            return branch_pipeline_jobs
        return self._get_branch_pipeline_jobs('main')

    def _get_branch_pipeline_jobs(self, branch_node_name: str) -> Optional[List[Job]]:
        if branch_node_name in self._gitlab_project_node:
            project_node = self._gitlab_project_node
        else:
            project_node = self._query_branch_pipelines(branch_node_name)

        pipeline_current_release = project_node[re.sub('[^A-Za-z0-9]+', '', branch_node_name)]['nodes']
        if pipeline_current_release:
            return [Job(node, pipeline_current_release[0]['ref']) for node in pipeline_current_release[0]['jobs']['nodes']]

    @staticmethod
    def _get_release_jobs(pipeline_jobs: Optional[dict], release_number: str) -> Dict[JobType,Job]:
        distros = {}
        if pipeline_jobs:
            for job in pipeline_jobs:
                if job.type in [JobType.BUILD, JobType.INSTALL, JobType.REPRO] and job.release == release_number:
                    distros.setdefault(job.distribution, {})
                    distros[job.distribution][job.type] = job
        return distros

    @property
    def name(self) -> str:
        return self._gitlab_project_node['name']

    @property
    def short_name(self) -> str:
        return self.name.removeprefix('qubes-')

    def get_current_release_pipeline(self, builder_configuration: Optional[dict]) -> Optional[dict]:
        if builder_configuration and 'branch' in builder_configuration:
            return self._get_pipeline_jobs(builder_configuration['branch'])
        return self._get_pipeline_jobs('current')

    def get_next_release_pipeline(self, builder_configuration: Optional[dict]) -> Optional[dict]:
        if builder_configuration and 'branch' in builder_configuration:
            return self._get_pipeline_jobs(builder_configuration['branch'])
        return self._get_pipeline_jobs('next')
    
    def get_current_release_jobs(self, release_number: str, builder_configuration: Optional[dict]) -> Dict[JobType,Job]:
        return self._get_release_jobs(self.get_current_release_pipeline(builder_configuration), release_number)
    
    def get_next_release_jobs(self, release_number: str, builder_configuration: Optional[dict]) -> Dict[JobType,Job]:
        return self._get_release_jobs(self.get_next_release_pipeline(builder_configuration), release_number)

    def _query_branch_pipelines(self, branch_name: str) -> dict:
        print(f"  -> Getting specific branch '{branch_name}' status")
        headers = {"Content-Type": "application/json", }
        query_pipeline = self._gitlab_query_pipeline_template.render(
            release_name=re.sub('[^A-Za-z0-9]+', '', branch_name),
            release_branch=branch_name
        )
        query_project_pipelines = self._gitlab_query_project_pipeline_template.render(
            project_name = self.name,
            pipelines = query_pipeline
        )
        r = requests.post('https://gitlab.com/api/graphql',
                          headers=headers,
                          json={"query": query_project_pipelines})
        return r.json()['data']['project']
