import os
import pandas as pd

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")


youtube = build("youtube", "v3", developerKey=API_KEY)


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


video_id = "Je7E8B8AmkQ"  # TODO: Vidoe id dalna hai

comments = get_comments(video_id)


df = pd.DataFrame(comments)

df.to_csv("comments.csv", index=False, encoding="utf-8-sig")


print(f"Successfully collected {len(df)} comments.")

print("\nFirst 5 comments:")
print(df.head())
