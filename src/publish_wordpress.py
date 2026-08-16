"""Publish a plot + text to a WordPress page via the REST API (Application Password auth)."""

import mimetypes
from pathlib import Path

import requests


def publish(
    image_path: str,
    page_id: int,
    html_content: str,
    wp_base_url: str,
    wp_user: str,
    wp_app_password: str,
) -> None:
    auth = (wp_user, wp_app_password)

    content_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
    with open(image_path, "rb") as f:
        media_resp = requests.post(
            f"{wp_base_url}/wp-json/wp/v2/media",
            auth=auth,
            headers={
                "Content-Disposition": f'attachment; filename="{Path(image_path).name}"',
                "Content-Type": content_type,
            },
            data=f.read(),
            timeout=30,
        )
    media_resp.raise_for_status()
    media_url = media_resp.json()["source_url"]

    page_resp = requests.post(
        f"{wp_base_url}/wp-json/wp/v2/pages/{page_id}",
        auth=auth,
        json={"content": html_content.replace("{{IMAGE_URL}}", media_url)},
        timeout=30,
    )
    page_resp.raise_for_status()
