import os
import re
import pandas as pd

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

youtube = build("youtube", "v3", developerKey=API_KEY)


def extract_video_id(url):

    patterns = [
        r"(?:v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:

        match = re.search(pattern, url)

        if match:
            return match.group(1)

    return None


def get_video_info(video_id):

    request = youtube.videos().list(part="snippet", id=video_id)

    response = request.execute()

    if not response["items"]:
        return None

    snippet = response["items"][0]["snippet"]

    return {
        "video_id": video_id,
        "video_title": snippet["title"],
        "channel_title": snippet["channelTitle"],
        "video_published_at": snippet["publishedAt"],
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
    }


def get_comments(video_id):

    comments = []

    next_page_token = None

    while True:

        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            textFormat="plainText",
            order="time",
            pageToken=next_page_token,
        )

        response = request.execute()

        for item in response["items"]:

            comment = item["snippet"]["topLevelComment"]["snippet"]

            comments.append(
                {
                    "comment_id": item["snippet"]["topLevelComment"]["id"],
                    "video_id": video_id,
                    "author": comment.get("authorDisplayName"),
                    "text": comment["textOriginal"],
                    "published_at": comment["publishedAt"],
                    "updated_at": comment.get("updatedAt"),
                    "like_count": comment.get("likeCount", 0),
                }
            )

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return comments


video_urls = [
    # TODO: Add your YouTube URLs here
    "https://www.youtube.com/watch?v=Je7E8B8AmkQ",
    "https://www.youtube.com/watch?v=BKgAk5vQlko",
    "https://www.youtube.com/watch?v=yFJDP7OinRM",
]


all_comments = []

for url in video_urls:

    print("\n========================================")
    print("Processing:")
    print(url)
    print("========================================")

    video_id = extract_video_id(url)

    if video_id is None:

        print("❌ Could not extract video ID.")

        continue

    print(f"Video ID: {video_id}")

    video_info = get_video_info(video_id)

    if video_info is None:

        print("❌ Video not found.")

        continue

    print(f"Title: {video_info['video_title']}")

    comments = get_comments(video_id)

    print(f"Comments collected: {len(comments)}")

    for comment in comments:

        comment["video_title"] = video_info["video_title"]

        comment["channel_title"] = video_info["channel_title"]

        comment["video_published_at"] = video_info["video_published_at"]

        comment["video_url"] = video_info["video_url"]

    all_comments.extend(comments)


df = pd.DataFrame(all_comments)


if not df.empty:

    df = df.drop_duplicates(subset=["comment_id"])


df.to_csv("youtube_comments_raw.csv", index=False, encoding="utf-8-sig")


print("\n\n========================================")
print("COLLECTION COMPLETED")
print("========================================")

print(f"Videos processed: {len(video_urls)}")

print(f"Total comments: {len(df)}")

print("\nColumns:")

print(df.columns.tolist())

print("\nComments per video:")

if not df.empty:

    print(df.groupby("video_title").size().sort_values(ascending=False))

print("\nDataset saved as:")

print("youtube_comments_raw.csv")
