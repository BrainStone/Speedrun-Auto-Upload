#!/usr/bin/env python3

import os

from livesplit_parser import LivesplitData

##############
# Settings
##############

SPLITS_DIR = '/home/yannick/LiveSplit/Splits'


##############
# Code
##############


def find_latest_record_file(search_path: str | os.PathLike) -> str | os.PathLike:
    """Find the most recently modified file in a directory and its subdirectories."""
    return max(
        (os.path.join(dirpath, filename) for dirpath, dirnames, filenames in os.walk(search_path) for filename in
         filenames), key=os.path.getmtime)


def find_latest_record(lss_path: str | os.PathLike):
    my_run = LivesplitData(lss_path)

    print('NUMBER OF ATTEMPTS:', my_run.num_attempts)
    print('NUMBER OF COMPLETED ATTEMPTS:', my_run.num_completed_attempts)
    print('PERCENTAGE OF RUNS COMPLETED:', my_run.percent_runs_completed)
    print('YOUR ATTEMPT DATA\n:', my_run.attempt_info_df)
    print('YOUR SPLIT DATA:\n', my_run.split_info_df)


if __name__ == "__main__":
    latest_record_file = find_latest_record_file(SPLITS_DIR)
    find_latest_record(latest_record_file)
