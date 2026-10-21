import os
import re
import time
import hashlib
import unicodedata
from datetime import datetime, timezone
from collections import defaultdict

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# PROTOTYPE 2.1
# CONTENT-DRIVEN MARATHI YOUTUBE COMMENT COLLECTION
# ============================================================

# ------------------------------------------------------------
# 1. CONFIGURATION
# ------------------------------------------------------------

API_KEY = os.getenv("YOUTUBE_API_KEY")

if not API_KEY:
    raise ValueError(
        "YOUTUBE_API_KEY environment variable not found."
    )

LEXICON_FILE = "offensive_lexicon.csv"

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# VIDEO DISCOVERY
# ============================================================

# IMPORTANT:
#
# These queries are ONLY used to discover ordinary Marathi
# content.
#
# Offensive words MUST NOT be placed here.
#
# Offensive lexicon is applied later to comments.

DISCOVERY_QUERIES = [

    # -------------------------
    # NEWS
    # -------------------------

    "Marathi news",
    "Marathi breaking news",
    "Maharashtra news",
    "Marathi latest news",
    "आजच्या बातम्या मराठी",
    "मराठी बातम्या",

    # -------------------------
    # LOCAL / MAHARASHTRA
    # -------------------------

    "Maharashtra local news",
    "Pune Marathi news",
    "Mumbai Marathi news",
    "Maharashtra latest updates",

    # -------------------------
    # SOCIAL ISSUES
    # -------------------------

    "Marathi social issues",
    "Maharashtra social issues",
    "Maharashtra public issues",
    "Marathi public discussion",

    # -------------------------
    # POLITICS / PUBLIC DISCUSSION
    # -------------------------

    "Marathi politics",
    "Maharashtra politics",
    "Marathi political discussion",
    "Marathi political debate",
    "मराठी राजकारण",

    # -------------------------
    # CRIME / CURRENT EVENTS
    # -------------------------

    "Marathi crime news",
    "Maharashtra crime news",
    "Marathi current affairs",
    "Maharashtra current affairs",

    # -------------------------
    # INTERVIEWS / DISCUSSION
    # -------------------------

    "Marathi interview",
    "Marathi discussion",
    "Marathi debate",
    "Marathi podcast",

    # -------------------------
    # ENTERTAINMENT
    # -------------------------

    "Marathi entertainment",
    "Marathi comedy",
    "Marathi movie discussion",
    "Marathi entertainment news",

    # -------------------------
    # CREATORS / VLOGS
    # -------------------------

    "Marathi vlog",
    "Marathi YouTuber",
    "Marathi creator",
    "Marathi daily vlog",

    # -------------------------
    # SHORTS / VIRAL
    # -------------------------

    "Marathi shorts",
    "Marathi viral shorts",
    "Marathi news shorts",
    "Marathi comedy shorts",
    "Marathi viral video",
]


# ============================================================
# COLLECTION LIMITS
# ============================================================

MAX_VIDEOS_PER_QUERY = 15

MAX_COMMENTS_PER_VIDEO = 150

MAX_CANDIDATES_PER_VIDEO = 30

MAX_VIDEOS_PER_CHANNEL = 5

MAX_TOTAL_CANDIDATES = 5000

# We also track raw comments.
MAX_TOTAL_RAW_COMMENTS = 10000

COLLECT_REPLIES = True

REGION_CODE = "IN"

# Do not make this a hard language filter.
# Marathi-English code-mixed content may not be classified
# correctly by YouTube metadata.

RELEVANCE_LANGUAGE = "mr"

SLEEP_BETWEEN_REQUESTS = 0.10


# ============================================================
# YOUTUBE CLIENT
# ============================================================

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)


# ============================================================
# LOAD OFFENSIVE LEXICON
# ============================================================

def load_lexicon(path):

    lexicon = pd.read_csv(path)

    if "keyword" not in lexicon.columns:
        raise ValueError(
            "offensive_lexicon.csv must contain "
            "a 'keyword' column."
        )

    lexicon["keyword"] = (
        lexicon["keyword"]
        .astype(str)
        .str.strip()
    )

    lexicon = lexicon[
        lexicon["keyword"].str.len() > 0
    ].copy()

    if "category" not in lexicon.columns:
        lexicon["category"] = "unknown"

    if "script" not in lexicon.columns:
        lexicon["script"] = "unknown"

    return lexicon


lexicon_df = load_lexicon(
    LEXICON_FILE
)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):

    if not isinstance(text, str):
        return ""

    text = unicodedata.normalize(
        "NFKC",
        text
    )

    text = text.lower()

    # Remove zero-width characters
    text = re.sub(
        r"[\u200b-\u200f\uFEFF]",
        "",
        text
    )

    # Normalize whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_for_matching(text):

    text = normalize_text(text)

    # Conservative repeated-character normalization.
    #
    # Example:
    # ganduuuuuuu -> gandu
    # muuurkh -> murkh
    #
    # Original comment is NEVER changed.

    text = re.sub(
        r"(.)\1{2,}",
        r"\1",
        text
    )

    return text


# ============================================================
# PREPARE LEXICON
# ============================================================

LEXICON = []

for _, row in lexicon_df.iterrows():

    normalized_keyword = normalize_for_matching(
        row["keyword"]
    )

    if not normalized_keyword:
        continue

    LEXICON.append({
        "keyword": row["keyword"],
        "normalized_keyword": normalized_keyword,
        "category": row["category"],
        "script": row["script"]
    })


print("=" * 75)
print("PROTOTYPE 2.1")
print("Content-driven Marathi YouTube comment collection")
print("=" * 75)

print(
    f"Lexicon terms       : {len(LEXICON)}"
)

print(
    f"Discovery queries   : {len(DISCOVERY_QUERIES)}"
)

print(
    f"Videos/query        : {MAX_VIDEOS_PER_QUERY}"
)

print(
    f"Comments/video      : {MAX_COMMENTS_PER_VIDEO}"
)

print(
    f"Max candidates/video: {MAX_CANDIDATES_PER_VIDEO}"
)

print(
    f"Max videos/channel : {MAX_VIDEOS_PER_CHANNEL}"
)

print()


# ============================================================
# COMMENT LEXICON MATCHING
# ============================================================

def find_matches(comment):

    normalized = normalize_for_matching(
        comment
    )

    matches = []

    for item in LEXICON:

        keyword = item[
            "normalized_keyword"
        ]

        if keyword in normalized:

            matches.append(item)

    return matches


# ============================================================
# SEARCH VIDEOS
# ============================================================

def search_videos(query):

    try:

        response = youtube.search().list(

            part="snippet",

            q=query,

            type="video",

            maxResults=MAX_VIDEOS_PER_QUERY,

            regionCode=REGION_CODE,

            relevanceLanguage=RELEVANCE_LANGUAGE,

            order="relevance"

        ).execute()

        time.sleep(
            SLEEP_BETWEEN_REQUESTS
        )

        return response.get(
            "items",
            []
        )

    except HttpError as e:

        print(
            f"[ERROR] Search failed "
            f"for '{query}': {e}"
        )

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
                youtube
                .commentThreads()
                .list(

                    part="snippet,replies",

                    videoId=video_id,

                    maxResults=min(
                        100,
                        MAX_COMMENTS_PER_VIDEO
                        - len(comments)
                    ),

                    pageToken=next_page_token,

                    textFormat="plainText"

                )
                .execute()
            )

            time.sleep(
                SLEEP_BETWEEN_REQUESTS
            )

        except HttpError as e:

            print(
                f"[WARNING] Comment "
                f"collection failed for "
                f"{video_id}: {e}"
            )

            break

        for item in response.get(
            "items",
            []
        ):

            top = (
                item["snippet"]
                ["topLevelComment"]
                ["snippet"]
            )

            comment_id = (
                item["snippet"]
                ["topLevelComment"]
                ["id"]
            )

            comments.append({

                "comment_id":
                    comment_id,

                "parent_comment_id":
                    "",

                "comment_text":
                    top.get(
                        "textDisplay",
                        ""
                    ),

                "published_at":
                    top.get(
                        "publishedAt"
                    ),

                "updated_at":
                    top.get(
                        "updatedAt"
                    ),

                "like_count":
                    top.get(
                        "likeCount",
                        0
                    ),

                "is_reply":
                    False
            })

            # ----------------------------------------------
            # REPLIES
            # ----------------------------------------------

            if COLLECT_REPLIES:

                replies = (
                    item
                    .get("replies", {})
                    .get("comments", [])
                )

                for reply in replies:

                    if (
                        len(comments)
                        >= MAX_COMMENTS_PER_VIDEO
                    ):
                        break

                    snippet = (
                        reply["snippet"]
                    )

                    comments.append({

                        "comment_id":
                            reply["id"],

                        "parent_comment_id":
                            snippet.get(
                                "parentId",
                                ""
                            ),

                        "comment_text":
                            snippet.get(
                                "textDisplay",
                                ""
                            ),

                        "published_at":
                            snippet.get(
                                "publishedAt"
                            ),

                        "updated_at":
                            snippet.get(
                                "updatedAt"
                            ),

                        "like_count":
                            snippet.get(
                                "likeCount",
                                0
                            ),

                        "is_reply":
                            True}
                    )

        next_page_token = response.get(
            "nextPageToken"
        )

        if not next_page_token:
            break

    return comments


# ============================================================
# COMMENT HASH
# ============================================================

def comment_hash(text):

    normalized = normalize_text(
        text
    )

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


# ============================================================
# STORAGE
# ============================================================

candidate_rows = []

video_rows = []

log_rows = []

seen_comments = set()

channel_video_count = defaultdict(int)

total_raw_comments = 0

total_candidates = 0


# ============================================================
# MAIN COLLECTION LOOP
# ============================================================

for query_index, query in enumerate(
    DISCOVERY_QUERIES,
    start=1
):

    print()
    print("=" * 75)
    print(
        f"[{query_index}/{len(DISCOVERY_QUERIES)}] "
        f"DISCOVERY QUERY: {query}"
    )
    print("=" * 75)

    videos = search_videos(
        query
    )

    print(
        f"Videos discovered: {len(videos)}"
    )

    query_raw_comments = 0

    query_candidates = 0

    processed_videos = 0

    skipped_channels = 0

    for video in videos:

        if (
            total_candidates
            >= MAX_TOTAL_CANDIDATES
        ):
            break

        if (
            total_raw_comments
            >= MAX_TOTAL_RAW_COMMENTS
        ):
            break

        video_id = video[
            "id"
        ]["videoId"]

        snippet = video[
            "snippet"
        ]

        channel_id = snippet.get(
            "channelId",
            ""
        )

        channel_name = snippet.get(
            "channelTitle",
            ""
        )

        video_title = snippet.get(
            "title",
            ""
        )

        # ----------------------------------------------------
        # CHANNEL DIVERSITY CONTROL
        # ----------------------------------------------------

        if (
            channel_video_count[
                channel_id
            ]
            >= MAX_VIDEOS_PER_CHANNEL
        ):

            skipped_channels += 1

            continue

        channel_video_count[
            channel_id
        ] += 1

        processed_videos += 1

        # ----------------------------------------------------
        # COLLECT COMMENTS
        # ----------------------------------------------------

        print()
        print(
            f"Video {processed_videos}: "
            f"{video_title[:90]}"
        )

        print(
            f"Channel: {channel_name}"
        )

        comments = get_comments(
            video_id
        )

        print(
            f"Raw comments: "
            f"{len(comments)}"
        )

        total_raw_comments += (
            len(comments)
        )

        query_raw_comments += (
            len(comments)
        )

        # ----------------------------------------------------
        # VIDEO METADATA
        # ----------------------------------------------------

        video_rows.append({

            "video_id":
                video_id,

            "video_title":
                video_title,

            "channel_id":
                channel_id,

            "channel_name":
                channel_name,

            "video_published_at":
                snippet.get(
                    "publishedAt"
                ),

            "discovery_query":
                query,

            "comments_collected":
                len(comments),

            "collected_at":
                datetime.now(
                    timezone.utc
                ).isoformat()

        })

        # ----------------------------------------------------
        # COMMENT PROCESSING
        # ----------------------------------------------------

        video_candidate_count = 0

        for comment in comments:

            if (
                total_candidates
                >= MAX_TOTAL_CANDIDATES
            ):
                break

            if (
                video_candidate_count
                >= MAX_CANDIDATES_PER_VIDEO
            ):
                break

            text = comment[
                "comment_text"
            ]

            if not text.strip():
                continue

            h = comment_hash(
                text
            )

            if h in seen_comments:
                continue

            # ------------------------------------------------
            # IMPORTANT:
            #
            # Offensive lexicon is used HERE.
            #
            # It was NOT used to find the video.
            # ------------------------------------------------

            matches = find_matches(
                text
            )

            if not matches:
                continue

            seen_comments.add(h)

            matched_keywords = [
                x["keyword"]
                for x in matches
            ]

            matched_categories = [
                x["category"]
                for x in matches
            ]

            matched_scripts = [
                x["script"]
                for x in matches
            ]

            candidate_rows.append({

                "comment_id":
                    comment[
                        "comment_id"
                    ],

                "parent_comment_id":
                    comment[
                        "parent_comment_id"
                    ],

                "comment_text":
                    text,

                "published_at":
                    comment[
                        "published_at"
                    ],

                "updated_at":
                    comment[
                        "updated_at"
                    ],

                "like_count":
                    comment[
                        "like_count"
                    ],

                "is_reply":
                    comment[
                        "is_reply"
                    ],

                "video_id":
                    video_id,

                "video_title":
                    video_title,

                "channel_id":
                    channel_id,

                "channel_name":
                    channel_name,

                "video_published_at":
                    snippet.get(
                        "publishedAt"
                    ),

                "discovery_query":
                    query,

                "matched_keyword":
                    "|".join(
                        matched_keywords
                    ),

                "matched_category":
                    "|".join(
                        matched_categories
                    ),

                "matched_script":
                    "|".join(
                        matched_scripts
                    ),

                "comment_hash":
                    h,

                "collected_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat()

            })

            video_candidate_count += 1

            query_candidates += 1

            total_candidates += 1

        print(
            f"Candidates from video: "
            f"{video_candidate_count}"
        )

    # --------------------------------------------------------
    # QUERY LOG
    # --------------------------------------------------------

    log_rows.append({

        "discovery_query":
            query,

        "videos_discovered":
            len(videos),

        "videos_processed":
            processed_videos,

        "channels_skipped":
            skipped_channels,

        "raw_comments_collected":
            query_raw_comments,

        "candidates_found":
            query_candidates,

        "collection_time":
            datetime.now(
                timezone.utc
            ).isoformat()

    })

    print()
    print(
        f"Query summary:"
    )

    print(
        f"  Raw comments : "
        f"{query_raw_comments}"
    )

    print(
        f"  Candidates   : "
        f"{query_candidates}"
    )

    # --------------------------------------------------------
    # GLOBAL LIMIT
    # --------------------------------------------------------

    if (
        total_candidates
        >= MAX_TOTAL_CANDIDATES
    ):
        print(
            "\nMaximum candidate limit reached."
        )
        break

    if (
        total_raw_comments
        >= MAX_TOTAL_RAW_COMMENTS
    ):
        print(
            "\nMaximum raw-comment limit reached."
        )
        break


# ============================================================
# CREATE DATAFRAMES
# ============================================================

candidates_df = pd.DataFrame(
    candidate_rows
)

videos_df = pd.DataFrame(
    video_rows
)

logs_df = pd.DataFrame(
    log_rows
)


# ============================================================
# SAVE
# ============================================================

candidate_path = os.path.join(
    OUTPUT_DIR,
    "offensive_candidates_v2_1.csv"
)

video_path = os.path.join(
    OUTPUT_DIR,
    "videos_collected_v2_1.csv"
)

log_path = os.path.join(
    OUTPUT_DIR,
    "collection_log_v2_1.csv"
)


candidates_df.to_csv(
    candidate_path,
    index=False,
    encoding="utf-8-sig"
)

videos_df.to_csv(
    video_path,
    index=False,
    encoding="utf-8-sig"
)

logs_df.to_csv(
    log_path,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# FINAL STATISTICS
# ============================================================

print()
print("=" * 75)
print("PROTOTYPE 2.1 COMPLETE")
print("=" * 75)

print(
    f"Videos collected       : "
    f"{len(videos_df)}"
)

if len(videos_df):

    print(
        f"Unique channels        : "
        f"{videos_df['channel_id'].nunique()}"
    )

else:

    print(
        "Unique channels        : 0"
    )


print(
    f"Raw comments inspected : "
    f"{total_raw_comments}"
)

print(
    f"Candidate comments     : "
    f"{len(candidates_df)}"
)


# ============================================================
# CANDIDATE STATISTICS
# ============================================================

if len(candidates_df) > 0:

    print()
    print("-" * 75)
    print("MATCHED KEYWORDS")
    print("-" * 75)

    print(
        candidates_df[
            "matched_keyword"
        ]
        .value_counts()
        .head(30)
    )

    print()
    print("-" * 75)
    print("MATCHED CATEGORIES")
    print("-" * 75)

    print(
        candidates_df[
            "matched_category"
        ]
        .value_counts()
    )

    print()
    print("-" * 75)
    print("DISCOVERY QUERY DISTRIBUTION")
    print("-" * 75)

    print(
        candidates_df[
            "discovery_query"
        ]
        .value_counts()
    )

    print()
    print("-" * 75)
    print("SOURCE CHANNEL DISTRIBUTION")
    print("-" * 75)

    print(
        candidates_df[
            "channel_name"
        ]
        .value_counts()
        .head(20)
    )

    print()
    print("-" * 75)
    print("SOURCE VIDEO DISTRIBUTION")
    print("-" * 75)

    print(
        candidates_df[
            "video_title"
        ]
        .value_counts()
        .head(20)
    )


# ============================================================
# FILES
# ============================================================

print()
print("=" * 75)
print("OUTPUT FILES")
print("=" * 75)

print(candidate_path)
print(video_path)
print(log_path)

print()
print(
    "IMPORTANT:"
)

print(
    "These are lexicon-matched CANDIDATES."
)

print(
    "They are NOT automatically labeled "
    "as offensive or hate speech."
)

print(
    "Human annotation is required."
)