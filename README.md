# Marathi YouTube Comment Collection Prototypes

This repository contains Python prototypes for collecting YouTube comments and identifying comments that match a configurable keyword lexicon. The later prototypes discover general Marathi-language videos first and apply the lexicon to their comments, rather than using potentially offensive words as video-search queries.

## Project structure

| Folder | Description |
| --- | --- |
| `prototype_1/` | Initial lexicon-driven collector. Searches videos using lexicon keywords, then collects and filters comments. |
| `prototype_2/` | Content-driven collector. Discovers general Marathi videos and filters their comments with the lexicon. |
| `prototype_2.1/` | Expanded content-driven collector with broader discovery queries and higher collection limits. |
| `youtube-comment-prototype/` | Small example that collects comments for a list of video URLs. |

Each of the first three folders has its own `offensive_lexicon.csv` and `output/` directory. Run a script from its own folder so its relative file paths resolve correctly.

## Requirements

- Python 3
- A Google/YouTube Data API v3 key
- Python packages: `pandas` and `google-api-python-client`
- Additionally, `tqdm` for `prototype_1/`
- Additionally, `python-dotenv` for `youtube-comment-prototype/`

Create and activate a virtual environment from the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pandas google-api-python-client tqdm python-dotenv
```

Set your API key in the same PowerShell session before running a collector:

```powershell
$env:YOUTUBE_API_KEY = "your-youtube-data-api-key"
```

Do not commit API keys. `prototype_2/`, `prototype_2.1/`, and `youtube-comment-prototype/` read `YOUTUBE_API_KEY` from the environment. **Security note:** `prototype_1/prototype1_offensive_collector.py` currently contains an API-key fallback in its source. Remove that fallback and rotate the key before publishing or continuing to use that prototype; prefer requiring the environment variable as the other collectors do.

## Run a prototype

From the repository root, run one of the following commands:

```powershell
Set-Location .\prototype_1
python .\prototype1_offensive_collector.py
```

```powershell
Set-Location .\prototype_2
python .\main.py
```

```powershell
Set-Location .\prototype_2.1
python .\main.py
```

For the URL-based example, edit the `video_urls` list in `collect_comments.py`, then run:

```powershell
Set-Location .\youtube-comment-prototype
python .\collect_comments.py
```

The collector scripts use the YouTube Data API. Requests are subject to API quota, permissions, rate limits, video availability, and whether comments are enabled.

## Lexicon format

The collector prototypes expect `offensive_lexicon.csv` in their working folder. Its columns are:

| Column | Purpose |
| --- | --- |
| `keyword` | Text to match in comments |
| `script` | Script or writing system for the keyword |
| `category` | Label used to categorize the keyword |

The URL-based example does not use a lexicon.

## Output

The first three prototypes create or update CSV files in their respective `output/` directories:

- `prototype_1/output/`: `videos_collected.csv`, `offensive_candidates.csv`, and `collection_log.csv`
- `prototype_2/output/`: `videos_collected_v2.csv`, `offensive_candidates_v2.csv`, and `collection_log_v2.csv`
- `prototype_2.1/output/`: `videos_collected_v2_1.csv`, `offensive_candidates_v2_1.csv`, and `collection_log_v2_1.csv`

The URL-based example writes `youtube_comments_raw.csv` in its working directory. These files can contain public comment text and associated metadata; handle and share collected data responsibly.
