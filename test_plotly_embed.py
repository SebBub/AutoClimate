"""One-off diagnostic: does an inline Plotly <script> embed survive a WordPress REST API
page update on abs-gruene.de, or does WordPress/NinjaFirewall strip or block it?

Not part of the AutoKlima pipeline — standalone, throwaway, targets the dummy test page (1090).
Runs either locally (conda env with plotly + requests, WP_* set as env vars) or via the
"Test Plotly WordPress embed" GitHub Actions workflow (workflow_dispatch, uses repo secrets).
"""

import os
import sys

import plotly.graph_objects as go
import requests

PAGE_ID = 1090


def main() -> None:
    wp_base_url = os.environ["WP_BASE_URL"].rstrip("/")
    auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])

    fig = go.Figure(data=go.Scatter(x=[1, 2, 3, 4], y=[10, 15, 13, 17], mode="lines+markers"))
    fig.update_layout(title="AutoKlima Plotly embed test")
    snippet = fig.to_html(full_html=False, include_plotlyjs="cdn")

    content = (
        "<p>Plotly embed test — if you can see an interactive line chart below "
        "(hover for tooltips, drag to zoom), the script survived.</p>\n" + snippet
    )
    print(f"Prepared {len(content)} bytes of content ({content.count('<script')} <script> tag(s)).")

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

    has_script_tag = "<script" in raw
    has_plotly_call = "Plotly.newPlot" in raw

    print("\n=== RESULT ===")
    print(f"<script> tag present in stored content: {has_script_tag}")
    print(f"Plotly.newPlot(...) call present in stored content: {has_plotly_call}")
    if has_script_tag and has_plotly_call:
        print("SURVIVED — the chart should render interactively on the live page.")
    elif not has_script_tag:
        print("STRIPPED — WordPress (wp_kses) or NinjaFirewall removed the <script> tag(s).")
    else:
        print("PARTIAL — a <script> tag survived but the Plotly call itself did not; inspect raw content below.")

    print(f"\nLive page to check visually: {wp_base_url}/?page_id={PAGE_ID}")
    print("\n--- Stored raw content (first 2000 chars) ---")
    print(raw[:2000])


if __name__ == "__main__":
    main()
