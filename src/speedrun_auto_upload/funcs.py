import datetime
import os
from dataclasses import dataclass
from typing import Generator

import dask.dataframe as dd
import ffmpeg
import pandas as pd
import tzlocal
from livesplit_parser import LivesplitData


@dataclass
class SpeedrunCategory:
    game: str
    category: str
    platform: str = "PC"

    @staticmethod
    def from_livesplit_data(data: LivesplitData) -> "SpeedrunCategory":
        return SpeedrunCategory(data.game_name, data.category_name, data.platform_name)


def find_latest_record_file(search_path: str | os.PathLike) -> str | os.PathLike:
    """Find the most recently modified file in a directory and its subdirectories."""
    return max(
        (
            os.path.join(dirpath, filename)
            for dirpath, dirnames, filenames in os.walk(search_path)
            for filename in filenames
        ),
        key=os.path.getmtime,
    )


def format_seconds(seconds: float, decimals: bool) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return (
        f"{hours:02.0f}:{minutes:02.0f}:{seconds:05.2f}"
        if decimals
        else f"{hours:02.0f}:{minutes:02.0f}:{seconds:02.0f}"
    )


def find_personal_best(lss_path: str | os.PathLike, short_category: bool) -> tuple[pd.Series, SpeedrunCategory]:
    """Find the personal best record for a given .lss file."""
    split_data = LivesplitData(lss_path, "GameTime")
    all_runs: pd.DataFrame = split_data.attempt_info_df
    completed_runs = all_runs.loc[all_runs["RunCompleted"]]

    if completed_runs.empty:
        raise ValueError("No completed runs found")

    personal_best = completed_runs.loc[completed_runs["GameTime_Sec"].idxmin()]
    # Timestamps are in UTC, convert them to local time, because all file names are in local time
    local_tzname = tzlocal.get_localzone().key
    personal_best["started"] = personal_best["started"].tz_localize("UTC").tz_convert(local_tzname).tz_localize(None)
    personal_best["ended"] = personal_best["ended"].tz_localize("UTC").tz_convert(local_tzname).tz_localize(None)
    personal_best["GameTime_Formatted"] = format_seconds(personal_best["GameTime_Sec"], short_category)

    return personal_best, SpeedrunCategory.from_livesplit_data(split_data)


def determine_timestamp_files(personal_best: pd.Series, videos_dir: str | os.PathLike) -> list[str | os.PathLike]:
    run_start: datetime.date = personal_best["started"].date()

    candidate_days = [run_start, run_start + datetime.timedelta(days=1)]

    candidate_file_names: Generator[str | os.PathLike, None, None] = (
        os.path.join(videos_dir, day.strftime("%Y-%m-%d.csv")) for day in candidate_days
    )
    file_names: list[str | os.PathLike] = list(filter(os.path.isfile, candidate_file_names))

    if not file_names:
        raise ValueError("No timestamp files found")

    return file_names


def load_timestamps(timestamp_files: list[str | os.PathLike], videos_dir: str | os.PathLike) -> pd.DataFrame:
    """Load timestamps from the specified timestamp files."""
    ddf = dd.read_csv(
        timestamp_files,
        sep=", ",
        usecols=[
            "Date Time",
            "Recording Filename",
            "Recording Timestamp",
            "Recording Timestamp on File",
        ],
        parse_dates=["Date Time"],
        engine="python",
    )
    ddf = ddf.set_index("Date Time", inplace=True)
    ddf = ddf.dropna(subset=["Recording Timestamp"])
    merged_timestamps = ddf.compute()

    artifical_timestamps = []

    # Add artificial timestamps for the start and end of each file, in case we forgot to add a marker before the
    # first run or a marker after the last run
    for video in merged_timestamps["Recording Filename"].unique():
        video_info = ffmpeg.probe(os.path.join(videos_dir, video))
        video_duration = int(float(video_info["format"]["duration"]))

        video_start_timestamp = datetime.datetime.strptime(video[:-4], "%Y-%m-%d_%H-%M-%S")
        video_end_timestamp = video_start_timestamp + datetime.timedelta(seconds=video_duration)

        artifical_timestamps.extend(
            [
                {
                    "Date Time": pd.to_datetime(video_start_timestamp),
                    "Recording Filename": video,
                    "Recording Timestamp": None,
                    "Recording Timestamp on File": None,
                },
                {
                    "Date Time": pd.to_datetime(video_end_timestamp),
                    "Recording Filename": video,
                    "Recording Timestamp": None,
                    "Recording Timestamp on File": None,
                },
            ]
        )

    artifical_timestamps = pd.DataFrame(artifical_timestamps)
    artifical_timestamps.set_index("Date Time", inplace=True)

    final_merged_timestamps = pd.concat([merged_timestamps, artifical_timestamps])
    final_merged_timestamps.sort_index(inplace=True)
    final_merged_timestamps["Recording Filepath"] = final_merged_timestamps["Recording Filename"].apply(
        lambda file: os.path.join(videos_dir, file)
    )

    return final_merged_timestamps


def determine_cut_data(
    timestamps: pd.DataFrame, personal_best: pd.Series
) -> tuple[str | os.PathLike, str | None, str | None]:
    start_row = timestamps.iloc[timestamps.index.searchsorted(personal_best["started"]) - 1]
    end_row = timestamps.iloc[timestamps.index.searchsorted(personal_best["ended"])]

    video_file = start_row["Recording Filepath"]
    start_timestamp = start_row["Recording Timestamp on File"]
    end_timestamp = end_row["Recording Timestamp on File"]

    return video_file, start_timestamp, end_timestamp


def generate_record_video_path(
    record_videos_dir: str | os.PathLike,
    personal_best: pd.Series,
    speedrun_category: SpeedrunCategory,
) -> str | os.PathLike:
    # Replace troublesome characters with similar looking ones
    manged_time = personal_best["GameTime_Formatted"].replace(":", "\uA789").replace(".", "\u2024")
    record_filename = f"{speedrun_category.game} - {speedrun_category.category} - {manged_time}.mkv"

    os.makedirs(record_videos_dir, exist_ok=True)

    return os.path.join(record_videos_dir, record_filename)


def cut_video(
    record_video_path: str | os.PathLike,
    video_file: str,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
):
    ffmpeg.input(video_file, ss=start_timestamp, to=end_timestamp).output(record_video_path, codec="copy").run()
