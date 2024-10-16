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


import argparse
import os
import sys


from pathlib import Path
from qubes_g2g_report.report_builder import ReportBuilder


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

        ReportBuilder(args.gitlab, args.current_release, args.next_release, gitlab_token).generate_report()
    except RuntimeError:
        sys.exit(1)
