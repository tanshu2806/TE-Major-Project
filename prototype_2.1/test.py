import os
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

youtube = build("youtube", "v3", developerKey=API_KEY)

print("YouTube API client initialized successfully!")

request = youtube.videos().list(part="snippet", id="dQw4w9WgXcQ")

response = request.execute()

print("API request successful!")
print("Videos found:", len(response.get("items", [])))
