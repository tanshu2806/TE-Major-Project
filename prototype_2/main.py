import hashlib
import os
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = os.getenv("YOUTUBE_API_KEY")

if not API_KEY:
    raise ValueError(
        "YOUTUBE_API_KEY environment variable not found.\n"
        "Set it before running the script."
    )

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

LEXICON_FILE = "offensive_lexicon.csv"


# ------------------------------------------------------------
# DISCOVERY SETTINGS
# ------------------------------------------------------------

# IMPORTANT:
# These are NOT offensive words.
# They are used only to discover normal Marathi content.

DISCOVERY_QUERIES = [
    "Marathi news",
    "Marathi breaking news",
    "Maharashtra news",
    "Marathi politics",
    "Marathi social issues",
    "Marathi crime news",
    "Marathi interview",
    "Marathi discussion",
    "Marathi comedy",
    "Marathi vlog",
    "Marathi shorts",
    "Marathi viral",
    "Marathi entertainment",
]


MAX_VIDEOS_PER_QUERY = 5

MAX_COMMENTS_PER_VIDEO = 100

# Maximum number of lexicon-matching candidates
# retained from a single video.
MAX_CANDIDATES_PER_VIDEO = 30

# Prevent one channel from dominating the dataset.
MAX_VIDEOS_PER_CHANNEL = 5

# Maximum total candidate comments.
MAX_TOTAL_CANDIDATES = 2000

COLLECT_REPLIES = True

REGION_CODE = "IN"

# Keep language filter loose because Marathi-English
# code-mixed content can be detected poorly by YouTube's
# language metadata.
RELEVANCE_LANGUAGE = "mr"

SLEEP_BETWEEN_REQUESTS = 0.1


# ============================================================
# YOUTUBE CLIENT
# ============================================================

youtube = build("youtube", "v3", developerKey=API_KEY)


# ============================================================
# LOAD LEXICON
# ============================================================


def load_lexicon(path):
    """
    Expected columns:

    keyword
    category
    script

    Example:

    gandu,profanity,roman
    गाढव,insult,devanagari
    murkh,insult,roman
    मूर्ख,insult,devanagari
    """

    lexicon = pd.read_csv(path)

    required = {"keyword"}

    missing = required - set(lexicon.columns)

    if missing:
        raise ValueError(f"Lexicon is missing columns: {missing}")

    lexicon["keyword"] = lexicon["keyword"].astype(str).str.strip()

    lexicon = lexicon[lexicon["keyword"].str.len() > 0].copy()

    if "category" not in lexicon.columns:
        lexicon["category"] = "unknown"

    if "script" not in lexicon.columns:
        lexicon["script"] = "unknown"

    return lexicon


lexicon_df = load_lexicon(LEXICON_FILE)


# ============================================================
# TEXT NORMALIZATION
# ============================================================


def normalize_text(text):
    """
    Normalization is ONLY used for matching.

    The original comment is always preserved.
    """

    if not isinstance(text, str):
        return ""

    text = unicodedata.normalize("NFKC", text)

    text = text.lower()

    # Remove zero-width characters
    text = re.sub(r"[\u200b-\u200f\uFEFF]", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_for_matching(text):
    """
    Additional normalization for informal spellings.

    Example:
        Ganduuuuuuuu -> ganduu
    """

    text = normalize_text(text)

    # Collapse repeated characters:
    #
    # goooooood -> good
    # ganduuuuu -> gandu
    #
    # Keep this conservative.
    text = re.sub(r"(.)\1{2,}", r"\1", text)

    return text


# ============================================================
# BUILD LEXICON
# ============================================================

LEXICON = []

for _, row in lexicon_df.iterrows():

    keyword = normalize_for_matching(row["keyword"])

    if not keyword:
        continue

    LEXICON.append(
        {
            "keyword": row["keyword"],
            "normalized_keyword": keyword,
            "category": row["category"],
            "script": row["script"],
        }
    )


print("=" * 70)
print("PROTOTYPE 2")
print("Content-driven Marathi YouTube comment collection")
print("=" * 70)

print(f"Lexicon terms : {len(LEXICON)}")
print(f"Discovery queries : {len(DISCOVERY_QUERIES)}")
print()


# ============================================================
# MATCH COMMENT AGAINST LEXICON
# ============================================================


def find_matches(comment):

    normalized = normalize_for_matching(comment)

    matches = []

    for item in LEXICON:

        keyword = item["normalized_keyword"]

        # Simple prototype-level matching.
        #
        # We deliberately do NOT use YouTube search
        # for these keywords.

        if keyword in normalized:

            matches.append(item)

    return matches


# ============================================================
# SEARCH FOR NORMAL MARATHI VIDEOS
# ============================================================


def search_videos(query):

    try:

        response = (
            youtube.search()
            .list(
                part="snippet",
                q=query,
                type="video",
                maxResults=MAX_VIDEOS_PER_QUERY,
                regionCode=REGION_CODE,
                relevanceLanguage=RELEVANCE_LANGUAGE,
                order="relevance",
            )
            .execute()
        )

        time.sleep(SLEEP_BETWEEN_REQUESTS)

        return response.get("items", [])

    except HttpError as e:

        print(f"[ERROR] Video search failed for " f"'{query}': {e}")

        return []


# ============================================================
# GET COMMENTS
# ============================================================


def get_comments(video_id):

    comments = []

    next_page_token = None

    while len(comments) < MAX_COMMENTS_PER_VIDEO:

        try:

            response = (
                youtube.commentThreads()
                .list(
                    part="snippet,replies",
                    videoId=video_id,
                    maxResults=min(100, MAX_COMMENTS_PER_VIDEO - len(comments)),
                    pageToken=next_page_token,
                    textFormat="plainText",
                )
                .execute()
            )

            time.sleep(SLEEP_BETWEEN_REQUESTS)

        except HttpError as e:

            print(f"[WARNING] Could not collect comments " f"for video {video_id}: {e}")

            break

        for item in response.get("items", []):

            top_comment = item["snippet"]["topLevelComment"]["snippet"]

            comments.append(
                {
                    "comment_id": item["snippet"]["topLevelComment"]["id"],
                    "parent_comment_id": "",
                    "comment_text": top_comment.get("textDisplay", ""),
                    "published_at": top_comment.get("publishedAt"),
                    "updated_at": top_comment.get("updatedAt"),
                    "like_count": top_comment.get("likeCount", 0),
                    "is_reply": False,
                }
            )

            # ------------------------------------------------
            # Replies
            # ------------------------------------------------

            if COLLECT_REPLIES:

                replies = item.get("replies", {}).get("comments", [])

                for reply in replies:

                    if len(comments) >= MAX_COMMENTS_PER_VIDEO:
                        break

                    reply_snippet = reply["snippet"]

                    comments.append(
                        {
                            "comment_id": reply["id"],
                            "parent_comment_id": reply_snippet.get("parentId", ""),
                            "comment_text": reply_snippet.get("textDisplay", ""),
                            "published_at": reply_snippet.get("publishedAt"),
                            "updated_at": reply_snippet.get("updatedAt"),
                            "like_count": reply_snippet.get("likeCount", 0),
                            "is_reply": True,
                        }
                    )

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return comments


# ============================================================
# HASH
# ============================================================


def comment_hash(text):

    normalized = normalize_text(text)

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ============================================================
# MAIN COLLECTION
# ============================================================

candidate_rows = []
video_rows = []
log_rows = []

seen_comments = set()

channel_video_count = defaultdict(int)

total_candidates = 0


for query in DISCOVERY_QUERIES:

    print()
    print("=" * 70)
    print(f"DISCOVERY QUERY: {query}")
    print("=" * 70)

    videos = search_videos(query)

    print(f"Videos discovered: {len(videos)}")

    query_candidates = 0

    for video in videos:

        if total_candidates >= MAX_TOTAL_CANDIDATES:
            print("\nMaximum total candidates reached.")
            break

        video_id = video["id"]["videoId"]

        snippet = video["snippet"]

        channel_id = snippet.get("channelId", "")

        channel_title = snippet.get("channelTitle", "")

        video_title = snippet.get("title", "")

        # ----------------------------------------------------
        # CHANNEL CONTROL
        # ----------------------------------------------------

        if channel_video_count[channel_id] >= MAX_VIDEOS_PER_CHANNEL:

            print(f"[SKIP CHANNEL LIMIT] " f"{channel_title}")

            continue

        channel_video_count[channel_id] += 1

        # ----------------------------------------------------
        # COLLECT COMMENTS
        # ----------------------------------------------------

        print(f"\nVideo: {video_title[:80]}")

        print(f"Channel: {channel_title}")

        comments = get_comments(video_id)

        print(f"Comments collected: {len(comments)}")

        video_candidate_count = 0

        # ----------------------------------------------------
        # SAVE VIDEO METADATA
        # ----------------------------------------------------

        video_rows.append(
            {
                "video_id": video_id,
                "video_title": video_title,
                "channel_id": channel_id,
                "channel_name": channel_title,
                "video_published_at": snippet.get("publishedAt"),
                "discovery_query": query,
                "comments_collected": len(comments),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        # ----------------------------------------------------
        # COMMENT LEVEL FILTER
        # ----------------------------------------------------

        for comment in comments:

            if total_candidates >= MAX_TOTAL_CANDIDATES:
                break

            if video_candidate_count >= MAX_CANDIDATES_PER_VIDEO:

                break

            text = comment["comment_text"]

            if not text.strip():
                continue

            h = comment_hash(text)

            if h in seen_comments:
                continue

            matches = find_matches(text)

            # ------------------------------------------------
            # NO MATCH -> NOT A CANDIDATE
            # ------------------------------------------------

            if not matches:
                continue

            seen_comments.add(h)

            # A comment may contain multiple
            # offensive terms.
            #
            # Store them together.

            matched_keywords = [x["keyword"] for x in matches]

            matched_categories = [x["category"] for x in matches]

            matched_scripts = [x["script"] for x in matches]

            candidate_rows.append(
                {
                    "comment_id": comment["comment_id"],
                    "parent_comment_id": comment["parent_comment_id"],
                    "comment_text": text,
                    "published_at": comment["published_at"],
                    "updated_at": comment["updated_at"],
                    "like_count": comment["like_count"],
                    "is_reply": comment["is_reply"],
                    "video_id": video_id,
                    "video_title": video_title,
                    "channel_id": channel_id,
                    "channel_name": channel_title,
                    "video_published_at": snippet.get("publishedAt"),
                    "discovery_query": query,
                    "matched_keyword": "|".join(matched_keywords),
                    "matched_category": "|".join(matched_categories),
                    "matched_script": "|".join(matched_scripts),
                    "comment_hash": h,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            video_candidate_count += 1
            query_candidates += 1
            total_candidates += 1

        print(f"Candidates from video: " f"{video_candidate_count}")

    log_rows.append(
        {
            "discovery_query": query,
            "videos_discovered": len(videos),
            "candidates_found": query_candidates,
            "collection_time": datetime.now(timezone.utc).isoformat(),
        }
    )

    if total_candidates >= MAX_TOTAL_CANDIDATES:

        break


# ============================================================
# SAVE OUTPUT
# ============================================================

candidates_df = pd.DataFrame(candidate_rows)

videos_df = pd.DataFrame(video_rows)

logs_df = pd.DataFrame(log_rows)


candidate_path = os.path.join(OUTPUT_DIR, "offensive_candidates_v2.csv")

video_path = os.path.join(OUTPUT_DIR, "videos_collected_v2.csv")

log_path = os.path.join(OUTPUT_DIR, "collection_log_v2.csv")


candidates_df.to_csv(candidate_path, index=False, encoding="utf-8-sig")

videos_df.to_csv(video_path, index=False, encoding="utf-8-sig")

logs_df.to_csv(log_path, index=False, encoding="utf-8-sig")


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("COLLECTION COMPLETE")
print("=" * 70)

print(f"Videos collected      : " f"{len(videos_df)}")

print(f"Unique channels     : {videos_df['channel_id'].nunique()}")

print(f"Candidate comments    : " f"{len(candidates_df)}")

if len(candidates_df):

    print()
    print("Matched keywords:")
    print(candidates_df["matched_keyword"].value_counts().head(20))

    print()
    print("Discovery queries:")
    print(candidates_df["discovery_query"].value_counts())

    print()
    print("Top source videos:")

    print(candidates_df[["video_title", "channel_name"]].value_counts().head(10))


print()
print("Files saved:")
print(candidate_path)
print(video_path)
print(log_path)

print()
print(
    "IMPORTANT: These are lexicon-matched "
    "CANDIDATE comments, NOT hate-speech labels."
)
