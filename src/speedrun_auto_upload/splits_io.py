from http import HTTPStatus

import requests


def upload_splits(file_path, api_token=None):
    # Step 1: Reserve the upload
    create_run_url = "https://splits.io/api/v4/runs"
    headers = {}

    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    create_response = requests.post(create_run_url, headers=headers)

    if create_response.status_code != HTTPStatus.CREATED:
        print("Failed to create a new run.")
        print("Status code:", create_response.status_code)
        print("Response:", create_response.text)
        return

    run_info = create_response.json()
    presigned_request = run_info["presigned_request"]
    s3_url = presigned_request["uri"]
    s3_method = presigned_request["method"]
    s3_fields = presigned_request["fields"]

    # Step 2: Upload the splits file to S3 using the presigned request
    with open(file_path, "rb") as file:
        files = {"file": file}
        upload_response = requests.request(s3_method, s3_url, data=s3_fields, files=files)

    if upload_response.status_code == HTTPStatus.NO_CONTENT:
        print("Upload successful!")
        print("Run ID:", run_info["id"])
        print("Claim URI:", run_info["uris"]["claim_uri"])
    else:
        print("Upload failed.")
        print("Status code:", upload_response.status_code)
        print("Response:", upload_response.text)
