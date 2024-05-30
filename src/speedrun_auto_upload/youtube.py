import json
import mimetypes
import os
from enum import Enum
from io import IOBase
from pathlib import Path
from typing import Union, AnyStr, IO

import googleapiclient.discovery
import googleapiclient.errors
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaIoBaseUpload, DEFAULT_CHUNK_SIZE
from tqdm import tqdm


class _ProgressIOWrapper(IOBase):
    """
    A wrapper designed for IO classes that wraps reading and seeking to update the progress bar.
    """

    def __init__(self, base_object: IO, progress_bar: tqdm):
        self._base_object = base_object
        self._progress_bar = progress_bar

        # Copy the base object's dictionary to the wrapper
        self.__dict__.update(base_object.__dict__)

    def seek(self, offset: int, whence: int = 0) -> int:
        res = self._base_object.seek(offset, whence)

        # Set progress bar to seeked position
        self._progress_bar.update(res - self._progress_bar.n)

        return res

    def read(self, n: int = -1) -> AnyStr:
        res = self._base_object.read(n)

        # Progress bar by
        self._progress_bar.update(len(res))

        return res

    def close(self):
        self._base_object.close()
        self._progress_bar.close()

    def __getattr__(self, item):
        # Forward attribute access to the base object if not found in the wrapper
        return getattr(self._base_object, item)

    def __setattr__(self, key, value):
        # Define a tuple of attributes that should be handled by the wrapper
        wrapper_attributes = ("_base_object", "_progress_bar")

        # Check if the attribute is meant to be handled by the wrapper
        if key in wrapper_attributes:
            super().__setattr__(key, value)
        else:
            # Otherwise, delegate the attribute setting to the base object
            setattr(self._base_object, key, value)


class TrackableMediaFileUpload(MediaIoBaseUpload):
    """A MediaUpload for a file where the read progress can be tracked.
    Copies MediaFileUpload but replaces the `open` call.

    Construct a MediaFileUpload and pass as the media_body parameter of the
    method. For example, if we had a service that allowed uploading images:

      media = TrackableMediaFileUpload('cow.png', mimetype='image/png',
        chunksize=1024*1024, resumable=True)
      farm.animals().insert(
          id='cow',
          name='cow.png',
          media_body=media).execute()

    Depending on the platform you are working on, you may pass -1 as the
    chunksize, which indicates that the entire file should be uploaded in a single
    request. If the underlying platform supports streams, such as Python 2.6 or
    later, then this can be very efficient as it avoids multiple connections, and
    also avoids loading the entire file into memory before sending it. Note that
    Google App Engine has a 5MB limit on request size, so you should never set
    your chunksize larger than 5MB, or to -1.
    """

    def __init__(
        self,
        filename: str | os.PathLike,
        mimetype: str | None = None,
        chunksize: int = DEFAULT_CHUNK_SIZE,
        resumable: bool = False,
        **tqdm_kwargs,
    ):
        """Constructor.

        Args:
          filename: string, Name of the file.
          mimetype: string, Mime-type of the file. If None then a mime-type will be
            guessed from the file extension.
          chunksize: int, File will be uploaded in chunks of this many bytes. Only
            used if resumable=True. Pass in a value of -1 if the file is to be
            uploaded in a single chunk. Note that Google App Engine has a 5MB limit
            on request size, so you should never set your chunksize larger than 5MB,
            or to -1.
          resumable: bool, True if this is a resumable upload. False means upload
            in a single request.
          **tqdm_kwargs: Arguments to be passed to the tqdm progress bar.
        """
        self._fd: IO | None = None
        self._fd_raw: IO | None = None
        self._filename = filename
        self._fd_raw = open(self._filename, "rb")

        if mimetype is None:
            # No mimetype provided, make a guess.
            mimetype, _ = mimetypes.guess_type(filename)
            if mimetype is None:
                # Guess failed, use octet-stream.
                mimetype = "application/octet-stream"

        super().__init__(self._fd_raw, mimetype, chunksize=chunksize, resumable=resumable)

        # Create Progress Bar
        tqdm_kwargs["total"] = self._size
        tqdm_kwargs["unit"] = "B"
        tqdm_kwargs["unit_scale"] = True
        tqdm_kwargs["unit_divisor"] = 1024
        if "desc" not in tqdm_kwargs:
            tqdm_kwargs["desc"] = "Uploading video"
        self._progress_bar = tqdm(**tqdm_kwargs)

        self._fd = _ProgressIOWrapper(self._fd_raw, self._progress_bar)

    def close(self):
        if self._progress_bar:
            self._progress_bar.close()
            self._progress_bar = None

        if self._fd_raw:
            self._fd_raw.close()
            # Deliberately don't close self._fd, because that would just close self._fd_raw and self._progress_bar
            self._fd_raw = None
            self._fd = None

    def __del__(self):
        self.close()

    def getbytes(self, begin, length):
        """Get bytes from the media.
        This override just reduces the calls to `update` of the progress bar

        Args:
          begin: int, offset from beginning of file.
          length: int, number of bytes to read, starting at begin.

        Returns:
          A string of bytes read. May be shorted than length if EOF was reached
          first.
        """
        self._fd_raw.seek(begin)
        read_res = self._fd_raw.read(length)

        # Calculate increment
        self._progress_bar.update(begin + len(read_res) - self._progress_bar.n)

        return read_res

    def to_json(self):
        """Creating a JSON representation of an instance of MediaFileUpload.

        Returns:
           string, a JSON representation of this instance, suitable to pass to
           from_json().
        """
        return self._to_json(strip=["_fd", "_fd_raw", "_progress_bar"])

    @staticmethod
    def from_json(s: str):
        d = json.loads(s)
        return TrackableMediaFileUpload(
            d["_filename"],
            mimetype=d["_mimetype"],
            chunksize=d["_chunksize"],
            resumable=d["_resumable"],
        )


class YouTube:
    class PrivacyStatus(Enum):
        PRIVATE = "private"
        UNLISTED = "unlisted"
        PUBLIC = "public"

    # Scopes required for uploading a video
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"

    # Path to the client secrets JSON file downloaded from Google Cloud Console
    CLIENT_SECRETS_FILE = "client_secrets.json"
    STORED_CREDENTIALS_FILE = ".stored_credentials.json"

    def __init__(self):
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        # The base dir where this module resides
        src_dir = Path(__file__).resolve().parent.parent

        # Try the module base dir, the one above and finally the CWD
        for storage_dir in [src_dir, src_dir.parent, Path.cwd()]:
            secrets_file = storage_dir / self.CLIENT_SECRETS_FILE

            if secrets_file.exists():
                break
        else:
            raise RuntimeError(f"No client secrets file found")

        # Set up the credentials file path
        credentials_file = storage_dir / self.STORED_CREDENTIALS_FILE

        # Load credentials from file if available
        if credentials_file.exists():
            credentials = Credentials.from_authorized_user_file(str(credentials_file))
            # Check if the credentials are expired and refresh if possible
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except RefreshError:
                    # If refresh fails, need to re-authenticate
                    credentials = self._authenticate(secrets_file)
        else:
            # Authenticate
            credentials = self._authenticate(secrets_file)

        # Save Credentials always
        self._save_credentials(credentials, credentials_file)

        return googleapiclient.discovery.build(self.API_SERVICE_NAME, self.API_VERSION, credentials=credentials)

    @classmethod
    def _authenticate(cls, secrets_file: Path) -> Credentials:
        # Get authentication
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), cls.SCOPES)
        credentials = flow.run_local_server(port=0)

        return credentials

    @staticmethod
    def _save_credentials(credentials: Credentials, credentials_file: Path):
        # Save credentials to file
        credentials_to_save = credentials.to_json()
        with open(credentials_file, "w") as f:
            f.write(credentials_to_save)
        # Ensure only we can read the file!
        credentials_file.chmod(0o600)

    def upload_video(
        self,
        video_filename: str | os.PathLike,
        title: str,
        description: str,
        tags: list[str],
        category_id: int | str,
        privacy_status: Union["YouTube.PrivacyStatus", str],
        made_for_kids: bool = False,
    ) -> str:
        if type(privacy_status) is YouTube.PrivacyStatus:
            privacy_status = privacy_status.value

        body = {
            "snippet": {"title": title, "description": description, "tags": tags, "categoryId": category_id},
            "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": made_for_kids},
        }

        # Upload the video (with a custom MediaFileUpload class to allow tracking of progress)
        media = TrackableMediaFileUpload(video_filename, chunksize=-1, resumable=True, desc="Uploading video")
        request = self.youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        # Upload video in as many requests as necessary
        response = None
        while response is None:
            _, response = request.next_chunk()

        # Close MediaUploader to finish the progress bar and close the underlying file
        media.close()

        print("Upload complete!")
        print(f"Video URL: https://www.youtube.com/watch?v={response['id']}")

        return response["id"]

    def add_video_to_playlist(self, video_id: str, playlist_id: str, position: int | None = None):
        body = {"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}

        if position is not None:
            body["snippet"]["position"] = position

        # Call the YouTube Data API to add the video to the playlist
        request = self.youtube.playlistItems().insert(part="snippet", body=body)
        request.execute()
