import os
from enum import Enum
from pathlib import Path
from typing import Union

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http
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

    def __init__(self):
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        src_dir = Path(__file__).resolve().parent.parent
        secrets_file = src_dir / YouTube.CLIENT_SECRETS_FILE

        if not secrets_file.exists():
            secrets_file = src_dir.parent / YouTube.CLIENT_SECRETS_FILE

        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(str(secrets_file), self.SCOPES)
        credentials = flow.run_local_server(port=0)
        return googleapiclient.discovery.build(self.API_SERVICE_NAME, self.API_VERSION, credentials=credentials)

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
        media = googleapiclient.http.MediaFileUpload(video_filename, chunksize=10 * 1024 * 1024, resumable=True)
        request = self.youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        # Use tqdm to create a progress bar
        with tqdm(total=media.size(), desc="Uploading video", unit="B", unit_scale=True, unit_divisor=1024) as pbar:
            response = None
            while response is None:
                status: googleapiclient.http.MediaUploadProgress
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
        response = request.execute()
