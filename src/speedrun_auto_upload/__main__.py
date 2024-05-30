#!/usr/bin/env python3

from speedrun_auto_upload.funcs import *

##############
# Settings
##############

SPLITS_DIR = "/home/yannick/LiveSplit/Splits/"
VIDEOS_DIR = "/home/yannick/Videos/OBS/"
SHORT_CATEGORY = "auto"
PLAYLIST_ID = "PLEewwzacolAKkvx-4sc0M83_V-Y-v705B"

##############
# Main
##############


if __name__ == "__main__":
    latest_record_file = find_latest_record_file(SPLITS_DIR)
    print(f"Latest record file: {latest_record_file}")

    personal_best, speedrun_category = find_personal_best(latest_record_file, SHORT_CATEGORY)
    print(f"Personal best:\n{personal_best}")
    print(f"Speedrun category: {speedrun_category}")

    timestamp_files = determine_timestamp_files(personal_best, VIDEOS_DIR)
    print(f"Timestamp files: {timestamp_files}")

    timestamps = load_timestamps(timestamp_files, VIDEOS_DIR)
    # print(f"Timestamps loaded:\n{timestamps}")

    video_file, start_timestamp, end_timestamp = determine_cut_data(timestamps, personal_best)
    # print(f"Cut data determined:\n{cut_data}")

    record_video_file = generate_record_video_path(
        os.path.join(VIDEOS_DIR, "Record Runs"), personal_best, speedrun_category
    )
    print(f"Record video file: {record_video_file}")

    cut_video(record_video_file, video_file, start_timestamp, end_timestamp)
    # Nothing to print

    upload_video(record_video_file, personal_best, speedrun_category, PLAYLIST_ID)
    # Nothing to print; video ID is printed already

    public_run_url, claim_run_url = upload_splits(latest_record_file)
    if claim_run_url is not None:
        print(f"Run was uploaded anonymously, claim it here: {claim_run_url}")
    print(f"Public run URL: {public_run_url}")
