# Wisburg Daily

Standalone GitHub Pages site for the versioned Wisburg Brief Document. The site has no
runtime backend: it reads `data/latest.json`, which is generated from the private MySQL
database by `fragments-of-market/backend/app/wisburg/daily.py`.

The published snapshot intentionally contains the complete Wisburg source bodies so a
reader can expand every referenced report. Do not add API keys, database configuration,
or raw `extra_json` fields to this repository.

## Local preview

```bash
python3 -m http.server 4174
open http://127.0.0.1:4174/
```

## Data contract

- `data/latest.json`: latest complete Beijing calendar-day brief.
- `data/index.json`: lightweight publication metadata.
- Historical briefs remain in private MySQL and are not accumulated in Git.

The publishing workflow must validate `schemaVersion`, all event/source references,
`meta.sourceBodiesIncluded=true`, and the deployed `briefDate`/`contentHash` before it
sends the Feishu notification.

