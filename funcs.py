import datetime
import os
from dataclasses import dataclass
from typing import Generator

import dask.dataframe as dd
import ffmpeg
import pandas as pd
from livesplit_parser import LivesplitData


@dataclass
class SpeedrunCategory:
    game: str
    category: str
    platform: str = 'PC'

    @staticmethod
    def from_livesplit_data(data: LivesplitData) -> 'SpeedrunCategory':
        return SpeedrunCategory(data.game_name, data.category_name, data.platform_name)


def find_latest_record_file(search_path: str | os.PathLike) -> str | os.PathLike:
    """Find the most recently modified file in a directory and its subdirectories."""
    return max(
        (os.path.join(dirpath, filename) for dirpath, dirnames, filenames in os.walk(search_path) for filename in
         filenames), key=os.path.getmtime)


def find_personal_best(lss_path: str | os.PathLike) -> tuple[pd.Series, SpeedrunCategory]:
    """Find the personal best record for a given .lss file."""
    split_data = LivesplitData(lss_path)
    all_runs: pd.DataFrame = split_data.attempt_info_df
    completed_runs = all_runs.loc[all_runs['RunCompleted']]

    if completed_runs.empty:
        raise ValueError("No completed runs found")

    return completed_runs.loc[completed_runs['RealTime_Sec'].idxmin()], SpeedrunCategory.from_livesplit_data(split_data)


def determine_timestamp_files(personal_best: pd.Series, videos_dir: str | os.PathLike) -> list[str | os.PathLike]:
    run_start: datetime.date = personal_best['started'].date()

    candidate_days = [run_start, run_start + datetime.timedelta(days=1)]

    candidate_file_names: Generator[str | os.PathLike, None, None] = (
        os.path.join(videos_dir, day.strftime('%Y-%m-%d.csv')) for day in candidate_days)
    file_names: list[str | os.PathLike] = list(filter(os.path.isfile, candidate_file_names))

    if not file_names:
        raise ValueError("No timestamp files found")

    return file_names


def load_timestamps(timestamp_files: list[str | os.PathLike], videos_dir: str | os.PathLike) -> pd.DataFrame:
    """Load timestamps from the specified timestamp files."""
    ddf = dd.read_csv(timestamp_files, sep=', ',
                      usecols=['Date Time', 'Recording Filename', 'Recording Timestamp', 'Recording Timestamp on File'],
                      parse_dates=['Date Time'], engine='python')
    ddf = ddf.set_index('Date Time', inplace=True)
    ddf = ddf.dropna(subset=['Recording Timestamp'])
    merged_timestamps = ddf.compute()

    artifical_timestamps = []

    # Add artificial timestamps for the start and end of each file, in case we forgot to add a marker before the
    # first run or a marker after the last run
    for video in merged_timestamps['Recording Filename'].unique():
        video_info = ffmpeg.probe(os.path.join(videos_dir, video))
        video_duration = int(float(video_info['format']['duration']))

        video_start_timestamp = datetime.datetime.strptime(video[:-4], '%Y-%m-%d_%H-%M-%S')
        video_end_timestamp = video_start_timestamp + datetime.timedelta(seconds=video_duration)

        artifical_timestamps.extend([
            {'Date Time': pd.to_datetime(video_start_timestamp), 'Recording Filename': video,
             'Recording Timestamp': None,
             'Recording Timestamp on File': None},
            {'Date Time': pd.to_datetime(video_end_timestamp), 'Recording Filename': video, 'Recording Timestamp': None,
             'Recording Timestamp on File': None},
        ])

    artifical_timestamps = pd.DataFrame(artifical_timestamps)
    artifical_timestamps.set_index('Date Time', inplace=True)

    final_merged_timestamps = pd.concat([merged_timestamps, artifical_timestamps])
    final_merged_timestamps.sort_index(inplace=True)

    return final_merged_timestamps


def determine_cut_data(timestamps: pd.DataFrame, personal_best: pd.Series):
    pass
