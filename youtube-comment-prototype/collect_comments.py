import os
import pandas as pd

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

youtube = build("youtube", "v3", developerKey=API_KEY)


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
        "published_at": snippet["publishedAt"],
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


video_id = "Je7E8B8AmkQ"

video_info = get_video_info(video_id)

if video_info is None:

    print("Video not found.")

else:

    comments = get_comments(video_id)

    df = pd.DataFrame(comments)

    df["video_title"] = video_info["video_title"]
    df["channel_title"] = video_info["channel_title"]
    df["video_published_at"] = video_info["published_at"]
    df["video_url"] = video_info["video_url"]

    df.to_csv("comments.csv", index=False, encoding="utf-8-sig")

    print("--------------------------------")
    print("Collection completed!")
    print("--------------------------------")

    print(f"Video: {video_info['video_title']}")
    print(f"Channel: {video_info['channel_title']}")
    print(f"Comments collected: {len(df)}")

    print("\nFirst 5 comments:")
    print(df[["text", "like_count", "published_at"]].head())
