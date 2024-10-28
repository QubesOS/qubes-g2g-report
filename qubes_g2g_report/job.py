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


from datetime import datetime
from qubes_g2g_report.enums.job_status import JobStatus
from qubes_g2g_report.enums.job_type import JobType
from typing import Optional


class Job:
    def __init__(self, gitlab_job_node: dict, branch: str):
        self._gitlab_job_node = gitlab_job_node
        self.branch = branch

    @property
    def creation_time(self) -> datetime:
        return datetime.fromisoformat(self._gitlab_job_node['createdAt'])

    @property
    def distribution(self) -> Optional[str]:
        try:
            return self.name.split(":")[2]
        except IndexError:
            return

    @property
    def name(self) -> str:
        return self._gitlab_job_node['name']

    @property
    def path(self) -> str:
        return self._gitlab_job_node['detailedStatus']['detailsPath']

    @property
    def release(self) -> str:
        return self.name.split(":")[0].removeprefix('r')

    @property
    def status(self) -> JobStatus:
        job_status_str = self._gitlab_job_node['detailedStatus']['text'].lower()
        if job_status_str in ["failed", "canceled", "skipped"]:
            return JobStatus.FAILURE

        if job_status_str in ["success", "passed"]:
            return JobStatus.SUCCESS

        return JobStatus.UNKNOWN

    @property
    def type(self) -> JobType:
        try:
            return JobType[self.name.split(":")[1].upper()]
        except (KeyError, IndexError):
            return JobType.UNKNOWN
