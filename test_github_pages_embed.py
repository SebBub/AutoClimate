"""One-off diagnostic: does an <iframe> pointing at a GitHub Pages-hosted Plotly chart
survive a WordPress REST API page update, avoiding the "Cross-site scripting" NinjaFirewall
signature that blocked the inline <script> version (incident #5139398)?

Not part of the AutoKlima pipeline — standalone, throwaway, targets the dummy test page (1090).
Called by the "Test GitHub Pages iframe embed" workflow with the deployed chart URL as argv[1].
"""

import os
import sys

import requests

PAGE_ID = 1090


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python test_github_pages_embed.py <chart_url>")
        sys.exit(1)
    chart_url = sys.argv[1]

    wp_base_url = os.environ["WP_BASE_URL"].rstrip("/")
    auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])

    content = (
        "<p>GitHub Pages iframe embed test — if you see an interactive line chart below "
        "(hover for tooltips, drag to zoom), the embed survived.</p>\n"
        f'<iframe src="{chart_url}" width="100%" height="500" style="border:none;" loading="lazy"></iframe>'
    )
    print(f"Chart URL: {chart_url}")
    print(f"Prepared {len(content)} bytes of content.")

    print(f"\nPOSTing to {wp_base_url}/wp-json/wp/v2/pages/{PAGE_ID} ...")
    post_resp = requests.post(
        f"{wp_base_url}/wp-json/wp/v2/pages/{PAGE_ID}",
        auth=auth,
        json={"content": content},
        timeout=30,
    )
    print(f"POST status: {post_resp.status_code}")
    if not post_resp.ok:
        print("--- Response body (first 2000 chars) ---")
        print(post_resp.text[:2000])
        sys.exit(1)

    print(f"\nGETting page {PAGE_ID} back with context=edit to inspect raw stored content ...")
    get_resp = requests.get(
        f"{wp_base_url}/wp-json/wp/v2/pages/{PAGE_ID}",
        auth=auth,
        params={"context": "edit"},
        timeout=30,
    )
    print(f"GET status: {get_resp.status_code}")
    if not get_resp.ok:
        print("--- Response body (first 2000 chars) ---")
        print(get_resp.text[:2000])
        sys.exit(1)

    try:
        raw = get_resp.json()["content"]["raw"]
    except (ValueError, KeyError) as exc:
        print(f"Could not parse raw content from response ({exc}); dumping full body:")
        print(get_resp.text[:3000])
        sys.exit(1)

    has_iframe = "<iframe" in raw

    print("\n=== RESULT ===")
    print(f"<iframe> tag present in stored content: {has_iframe}")
    if has_iframe:
        print("SURVIVED — the chart should render on the live page (check the URL below).")
    else:
        print("STRIPPED — WordPress (wp_kses) or NinjaFirewall removed the <iframe> tag.")

    print(f"\nLive page to check visually: {wp_base_url}/?page_id={PAGE_ID}")
    print("\n--- Stored raw content (first 2000 chars) ---")
    print(raw[:2000])


if __name__ == "__main__":
    main()
