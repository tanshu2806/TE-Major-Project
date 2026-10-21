import os
import re
import time
import hashlib
from datetime import datetime, timezone

import pandas as pd
from tqdm import tqdm
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = os.getenv("YOUTUBE_API_KEY", "AIzaSyDnu97VanurFpM1R9DKzjldeUouWev9KxE")

LEXICON_FILE = "offensive_lexicon.csv"
OUTPUT_DIR = "output"

# Prototype limits
MAX_VIDEOS_PER_KEYWORD = 5
MAX_COMMENTS_PER_VIDEO = 100

# IMPORTANT:
# Maximum number of candidate comments retained per keyword.
# This follows the paper's idea of limiting retrieval per query
# to reduce over-representation of particular words.
MAX_CANDIDATES_PER_KEYWORD = 150

# Include replies?
COLLECT_REPLIES = True

# Search settings
SEARCH_REGION = "IN"
SEARCH_LANGUAGE = "mr"

# YouTube search order
SEARCH_ORDER = "relevance"

# Small delay to be gentle with the API
REQUEST_DELAY = 0.2


# ============================================================
# SETUP
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

if API_KEY == "PASTE_YOUR_API_KEY_HERE":
    raise ValueError(
        "YouTube API key not configured.\n"
        "Set YOUTUBE_API_KEY or put your key in API_KEY."
    )

youtube = build("youtube", "v3", developerKey=API_KEY)


# ============================================================
# HELPERS
# ============================================================


def normalize_text(text):
    """
    Basic normalization ONLY for matching/deduplication.

    The original comment is always preserved.
    """
    if not isinstance(text, str):
        return ""

    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_comment_hash(text):
    """
    Creates a hash useful for detecting duplicate comment text.
    """
    normalized = normalize_text(text)

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def safe_request(request_func, **kwargs):
    """
    Wrapper around YouTube API requests.
    """
    while True:
        try:
            return request_func(**kwargs).execute()

        except HttpError as e:

            status = getattr(e.resp, "status", None)

            if status == 403:
                print("\n[ERROR] YouTube API quota/permission issue.")
                print(e)
                return None

            if status == 429:
                print("\n[WARNING] Rate limit reached. Waiting...")
                time.sleep(10)
                continue

            print("\n[ERROR] YouTube API request failed:")
            print(e)
            return None

        except Exception as e:
            print("\n[ERROR] Unexpected API error:")
            print(e)
            return None


# ============================================================
# LOAD LEXICON
# ============================================================


def load_lexicon():

    if not os.path.exists(LEXICON_FILE):
        raise FileNotFoundError(f"Could not find {LEXICON_FILE}")

    df = pd.read_csv(LEXICON_FILE)

    required_columns = {"keyword", "script", "category"}

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(f"Missing columns in lexicon: {missing}")

    df["keyword"] = df["keyword"].astype(str).str.strip()

    df = df[df["keyword"].str.len() > 0].copy()

    df = df.drop_duplicates(subset=["keyword"])

    return df


# ============================================================
# SEARCH YOUTUBE VIDEOS
# ============================================================


def search_videos(keyword):

    videos = []

    next_page_token = None

    while len(videos) < MAX_VIDEOS_PER_KEYWORD:

        remaining = MAX_VIDEOS_PER_KEYWORD - len(videos)

        response = safe_request(
            youtube.search().list,
            part="snippet",
            q=keyword,
            type="video",
            maxResults=min(50, remaining),
            pageToken=next_page_token,
            regionCode=SEARCH_REGION,
            relevanceLanguage=SEARCH_LANGUAGE,
            order=SEARCH_ORDER,
        )

        if response is None:
            break

        for item in response.get("items", []):

            video_id = item.get("id", {}).get("videoId")

            if not video_id:
                continue

            snippet = item.get("snippet", {})

            videos.append(
                {
                    "video_id": video_id,
                    "video_title": snippet.get("title", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "channel_name": snippet.get("channelTitle", ""),
                    "video_published_at": snippet.get("publishedAt", ""),
                    "search_keyword": keyword,
                }
            )

            if len(videos) >= MAX_VIDEOS_PER_KEYWORD:
                break

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

        time.sleep(REQUEST_DELAY)

    return videos


# ============================================================
# GET VIDEO COMMENTS
# ============================================================


def get_comments(video_id):

    comments = []

    next_page_token = None

    while len(comments) < MAX_COMMENTS_PER_VIDEO:

        remaining = MAX_COMMENTS_PER_VIDEO - len(comments)

        response = safe_request(
            youtube.commentThreads().list,
            part="snippet,replies",
            videoId=video_id,
            maxResults=min(100, remaining),
            pageToken=next_page_token,
            textFormat="plainText",
        )

        if response is None:
            break

        for item in response.get("items", []):

            thread_snippet = item.get("snippet", {})

            top_comment = thread_snippet.get("topLevelComment", {})

            top_snippet = top_comment.get("snippet", {})

            comment = {
                "comment_id": top_comment.get("id", ""),
                "parent_comment_id": "",
                "comment_text": top_snippet.get("textDisplay", ""),
                "published_at": top_snippet.get("publishedAt", ""),
                "updated_at": top_snippet.get("updatedAt", ""),
                "like_count": top_snippet.get("likeCount", 0),
                "is_reply": 0,
            }

            comments.append(comment)

            # ------------------------------------------------
            # Replies
            # ------------------------------------------------

            if COLLECT_REPLIES:

                replies = item.get("replies", {}).get("comments", [])

                for reply in replies:

                    reply_snippet = reply.get("snippet", {})

                    comments.append(
                        {
                            "comment_id": reply.get("id", ""),
                            "parent_comment_id": top_comment.get("id", ""),
                            "comment_text": reply_snippet.get("textDisplay", ""),
                            "published_at": reply_snippet.get("publishedAt", ""),
                            "updated_at": reply_snippet.get("updatedAt", ""),
                            "like_count": reply_snippet.get("likeCount", 0),
                            "is_reply": 1,
                        }
                    )

            if len(comments) >= MAX_COMMENTS_PER_VIDEO:
                break

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

        time.sleep(REQUEST_DELAY)

    return comments[:MAX_COMMENTS_PER_VIDEO]


# ============================================================
# KEYWORD MATCHING
# ============================================================


def find_matching_keywords(comment_text, lexicon):

    normalized_comment = normalize_text(comment_text)

    matches = []

    for _, row in lexicon.iterrows():

        keyword = str(row["keyword"]).strip()

        normalized_keyword = normalize_text(keyword)

        if not normalized_keyword:
            continue

        # For prototype:
        # simple substring matching.
        if normalized_keyword in normalized_comment:

            matches.append(
                {
                    "keyword": keyword,
                    "script": row["script"],
                    "category": row["category"],
                }
            )

    return matches


# ============================================================
# MAIN COLLECTION
# ============================================================


def main():

    print("=" * 70)
    print("PROTOTYPE 1 — MARATHI OFFENSIVE COMMENT COLLECTOR")
    print("=" * 70)

    lexicon = load_lexicon()

    print(f"\nLoaded {len(lexicon)} lexical terms.")

    all_videos = []
    all_candidates = []
    collection_log = []

    global_comment_hashes = set()

    # --------------------------------------------------------
    # Process every keyword
    # --------------------------------------------------------

    for _, lex_row in tqdm(
        lexicon.iterrows(), total=len(lexicon), desc="Processing keywords"
    ):

        keyword = str(lex_row["keyword"]).strip()

        print(f"\n\nSearching for: {keyword}")

        start_time = time.time()

        videos = search_videos(keyword)

        print(f"Videos found: {len(videos)}")

        keyword_candidate_count = 0
        keyword_raw_count = 0

        for video in videos:

            video_id = video["video_id"]

            # Store video information
            all_videos.append(video)

            comments = get_comments(video_id)

            keyword_raw_count += len(comments)

            for comment in comments:

                text = comment["comment_text"]

                if not text.strip():
                    continue

                matches = find_matching_keywords(text, lexicon)

                if not matches:
                    continue

                # ------------------------------------------------
                # Prevent duplicate comment text
                # ------------------------------------------------

                comment_hash = make_comment_hash(text)

                if comment_hash in global_comment_hashes:
                    continue

                global_comment_hashes.add(comment_hash)

                matched_terms = [m["keyword"] for m in matches]

                matched_categories = [m["category"] for m in matches]

                matched_scripts = [m["script"] for m in matches]

                candidate = {
                    **comment,
                    "video_id": video["video_id"],
                    "video_title": video["video_title"],
                    "channel_id": video["channel_id"],
                    "channel_name": video["channel_name"],
                    "video_published_at": video["video_published_at"],
                    "search_keyword": keyword,
                    "matched_keyword": "|".join(matched_terms),
                    "matched_script": "|".join(matched_scripts),
                    "matched_category": "|".join(matched_categories),
                    "comment_hash": comment_hash,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }

                all_candidates.append(candidate)

                keyword_candidate_count += 1

                # ------------------------------------------------
                # Per-keyword sampling limit
                # ------------------------------------------------

                if keyword_candidate_count >= MAX_CANDIDATES_PER_KEYWORD:
                    break

            if keyword_candidate_count >= MAX_CANDIDATES_PER_KEYWORD:
                break

        elapsed = time.time() - start_time

        collection_log.append(
            {
                "keyword": keyword,
                "script": lex_row["script"],
                "category": lex_row["category"],
                "videos_found": len(videos),
                "raw_comments_checked": keyword_raw_count,
                "candidate_comments": keyword_candidate_count,
                "time_seconds": round(elapsed, 2),
                "collection_time": datetime.now(timezone.utc).isoformat(),
            }
        )

        print(f"Candidate comments: " f"{keyword_candidate_count}")

    # ========================================================
    # SAVE RESULTS
    # ========================================================

    videos_df = pd.DataFrame(all_videos)

    candidates_df = pd.DataFrame(all_candidates)

    log_df = pd.DataFrame(collection_log)

    # Remove duplicate videos
    if not videos_df.empty:

        videos_df = videos_df.drop_duplicates(subset=["video_id"])

    # Save
    videos_path = os.path.join(OUTPUT_DIR, "videos_collected.csv")

    candidates_path = os.path.join(OUTPUT_DIR, "offensive_candidates.csv")

    log_path = os.path.join(OUTPUT_DIR, "collection_log.csv")

    videos_df.to_csv(videos_path, index=False, encoding="utf-8-sig")

    candidates_df.to_csv(candidates_path, index=False, encoding="utf-8-sig")

    log_df.to_csv(log_path, index=False, encoding="utf-8-sig")

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print("\n")
    print("=" * 70)
    print("COLLECTION COMPLETE")
    print("=" * 70)

    print(f"Unique videos: " f"{len(videos_df)}")

    print(f"Candidate comments: " f"{len(candidates_df)}")

    print(f"Keywords processed: " f"{len(lexicon)}")

    print("\nFiles created:")

    print(f"  {videos_path}")

    print(f"  {candidates_path}")

    print(f"  {log_path}")

    print("\nIMPORTANT:")
    print("These are CANDIDATE offensive comments.")
    print("They are NOT automatically hate-speech labels.")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
