#!/usr/bin/env python3
"""Publish an approved clip. NEVER call this without explicit user approval.

Targets:
  youtube — official YouTube Data API v3 (Shorts are just vertical videos)
            Needs: pip install google-api-python-client google-auth-oauthlib
            and an OAuth client file (env YT_CLIENT_SECRETS, default
            ~/.config/clip-skill/client_secrets.json). First run opens a
            browser for consent; the token is cached for next time.
  webhook — POSTs the clip + metadata as multipart/form-data to a URL
            (env WEBHOOK_URL or --url). Use with n8n/Zapier to fan out to
            TikTok, Instagram, Discord, etc.

Usage:
    python3 publish.py clip.mp4 --target youtube --title "..." \
        [--description "..."] [--tags tag1,tag2] [--privacy unlisted] [--dry-run]
    python3 publish.py clip.mp4 --target webhook --url https://... [--dry-run]
"""

import argparse
import json
import os
import sys
from pathlib import Path

TOKEN_PATH = Path.home() / ".config" / "clip-skill" / "yt_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def publish_youtube(args) -> dict:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise SystemExit(
            "missing deps: pip install google-api-python-client google-auth-oauthlib"
        )

    secrets = os.environ.get(
        "YT_CLIENT_SECRETS",
        str(Path.home() / ".config" / "clip-skill" / "client_secrets.json"),
    )
    if not Path(secrets).exists():
        raise SystemExit(
            f"OAuth client file not found at {secrets}.\n"
            "Create one (Desktop app) at https://console.cloud.google.com/apis/credentials\n"
            "with the YouTube Data API v3 enabled, then set YT_CLIENT_SECRETS."
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": args.title,
            "description": args.description or "",
            "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
            "categoryId": "22",
        },
        "status": {"privacyStatus": args.privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(args.clip, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _status, response = request.next_chunk()
    return {
        "target": "youtube",
        "video_id": response["id"],
        "url": f"https://youtube.com/shorts/{response['id']}",
        "privacy": args.privacy,
    }


def publish_webhook(args) -> dict:
    import httpx

    url = args.url or os.environ.get("WEBHOOK_URL")
    if not url:
        raise SystemExit("webhook target needs --url or WEBHOOK_URL env var")

    metadata = {
        "title": args.title or Path(args.clip).stem,
        "description": args.description or "",
        "tags": args.tags or "",
    }
    with open(args.clip, "rb") as f:
        resp = httpx.post(
            url,
            data=metadata,
            files={"file": (Path(args.clip).name, f, "video/mp4")},
            timeout=300,
        )
    resp.raise_for_status()
    return {"target": "webhook", "url": url, "status_code": resp.status_code}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clip")
    parser.add_argument("--target", required=True, choices=["youtube", "webhook"])
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--tags", help="comma-separated")
    parser.add_argument("--privacy", default="unlisted",
                        choices=["public", "unlisted", "private"])
    parser.add_argument("--url", help="webhook URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not Path(args.clip).exists():
        print(f"clip not found: {args.clip}", file=sys.stderr)
        return 1
    if args.target == "youtube" and not args.title:
        print("youtube target requires --title", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps({
            "dry_run": True, "target": args.target, "clip": args.clip,
            "title": args.title, "privacy": args.privacy,
            "size_mb": round(Path(args.clip).stat().st_size / 1e6, 1),
        }))
        return 0

    result = publish_youtube(args) if args.target == "youtube" else publish_webhook(args)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
