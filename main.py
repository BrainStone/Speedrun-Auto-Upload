#!/usr/bin/env python3

import os

from livesplit_parser import LivesplitData
from pandas import Series, DataFrame

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


def find_personal_best(lss_path: str | os.PathLike) -> Series:
    """Find the personal best record for a given .lss file."""
    split_data = LivesplitData(lss_path)
    all_runs: DataFrame = split_data.attempt_info_df
    completed_runs = all_runs.loc[all_runs['RunCompleted']]

    if completed_runs.empty:
        raise ValueError("No completed runs found")

    return completed_runs.loc[completed_runs['RealTime_Sec'].idxmin()]


if __name__ == "__main__":
    latest_record_file = find_latest_record_file(SPLITS_DIR)
    print(f"Latest record file: {latest_record_file}")

    personal_best = find_personal_best(latest_record_file)
    print(f"Personal best: {personal_best}")
