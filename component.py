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


from typing import Optional


class Component:
    def __init__(self, gitlab_project_node: dict):
        self._gitlab_project_node = gitlab_project_node
    
    def _get_pipeline_jobs(self, branch_node_name: str) -> Optional[dict]:
        branch_pipeline_jobs = self._get_branch_pipeline_jobs(branch_node_name)
        if branch_pipeline_jobs is not None:
            return branch_pipeline_jobs
        return self._get_branch_pipeline_jobs('main')

    def _get_branch_pipeline_jobs(self, branch_node_name: str) -> Optional[dict]:
        pipeline_current_release = self._gitlab_project_node[branch_node_name]['nodes']
        if pipeline_current_release:
            return pipeline_current_release[0]['jobs']['nodes']
    
    def _get_release_status(self, pipeline_jobs: Optional[dict], release_number: str) -> dict:
        distros = {}
        if pipeline_jobs:
            for job in pipeline_jobs:
                job_name = job['name']
                splitted_job_name = job_name.split(':')
                if len(splitted_job_name) == 3:
                    job_release_number, job_stage, distro_name = splitted_job_name
                    if job_release_number == f"r{release_number}":
                        if job_stage in ['build', 'install', 'repro']:
                            distros.setdefault(distro_name, {})
                            distros[distro_name][job_stage] = job['detailedStatus']
                        
        return distros

    @property
    def name(self) -> str:
        return self._gitlab_project_node['name']

    @property
    def short_name(self) -> str:
        return self.name.lstrip('qubes-')

    @property
    def current_release_pipeline(self) -> Optional[dict]:
        return self._get_pipeline_jobs('current')
    
    @property
    def next_release_pipeline(self) -> Optional[dict]:
        return self._get_pipeline_jobs('next')
    
    def get_current_release_status(self, release_number: int) -> dict:
        return self._get_release_status(self.current_release_pipeline, release_number)
    
    def get_next_release_status(self, release_number: int) -> dict:
        return self._get_release_status(self.next_release_pipeline, release_number)
