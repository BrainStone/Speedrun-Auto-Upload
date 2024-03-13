#!/usr/bin/env python3

from funcs import *

##############
# Settings
##############

SPLITS_DIR = '/home/yannick/LiveSplit/Splits/'
VIDEOS_DIR = '/home/yannick/Videos/OBS/'

##############
# Main
##############


if __name__ == "__main__":
    latest_record_file = find_latest_record_file(SPLITS_DIR)
    print(f"Latest record file: {latest_record_file}")

    personal_best, speedrun_category = find_personal_best(latest_record_file)
    print(f"Personal best:\n{personal_best}")
    print(f"Speedrun category: {speedrun_category}")

    timestamp_files = determine_timestamp_files(personal_best, VIDEOS_DIR)
    print(f"Timestamp files: {timestamp_files}")

    timestamps = load_timestamps(timestamp_files, VIDEOS_DIR)
    print(f"Timestamps loaded:\n{timestamps}")
