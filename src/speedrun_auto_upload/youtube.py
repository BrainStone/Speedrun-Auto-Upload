import os
from enum import Enum
from pathlib import Path
from typing import Union

import googleapiclient.discovery
import googleapiclient.errors
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload, MediaUploadProgress
from tqdm import tqdm


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
                    credentials = self._authenticate_and_save(secrets_file, credentials_file)
        else:
            # Authenticate and save credentials
            credentials = self._authenticate_and_save(secrets_file, credentials_file)

        return googleapiclient.discovery.build(self.API_SERVICE_NAME, self.API_VERSION, credentials=credentials)

    def _authenticate_and_save(self, secrets_file: Path, credentials_file: Path):
        # Get authentication
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), self.SCOPES)
        credentials = flow.run_local_server(port=0)

        # Save credentials to file
        credentials_to_save = credentials.to_json()
        with open(credentials_file, 'w') as f:
            f.write(credentials_to_save)
        # Ensure only we can read the file!
        credentials_file.chmod(0o600)

        return credentials

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

        # Upload the video (in 10 MiB chunks)
        #  10 MiB -> 5.03 MiB/s -> 15:08
        # 100 MiB -> 5.10 MiB/s ->
        media = MediaFileUpload(video_filename, chunksize=100 * 1024 * 1024, resumable=True)
        request = self.youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        # Use tqdm to create a progress bar
        with tqdm(total=media.size(), desc="Uploading video", unit="B", unit_scale=True, unit_divisor=1024) as pbar:
            response = None
            while response is None:
                status: MediaUploadProgress
                status, response = request.next_chunk()
                if status:
                    pbar.update(status.resumable_progress - pbar.n)

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
