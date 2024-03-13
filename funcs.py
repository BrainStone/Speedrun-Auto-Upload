import datetime
import os
from dataclasses import dataclass
from typing import Generator

import pandas as pd
import dask.dataframe as dd
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


def load_timestamps(timestamp_files: list[str | os.PathLike]) -> pd.DataFrame:
    """Load timestamps from the specified timestamp files."""
    ddf = dd.read_csv(timestamp_files, sep=', ', parse_dates=['Date Time'], engine='python')
    ddf = ddf.set_index('Date Time', inplace=True)
    ddf = ddf.dropna(subset=['Recording Timestamp'])

    return ddf.compute()
