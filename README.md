# Wisburg Daily

Standalone GitHub Pages site for the versioned Wisburg Brief Document. The site has no
runtime backend: it reads `data/latest.json`, which is generated from the private MySQL
database by `fragments-of-market/backend/app/wisburg/daily.py`.

The published snapshot contains the complete Wisburg source bodies inside an AES-GCM
encrypted envelope. The access answer is read from the private workspace at publish time
and is never committed. Do not add API keys, passwords, database configuration, plaintext
report bodies, or raw `extra_json` fields to this repository.

## Local preview

```bash
python3 -m http.server 4174
open http://127.0.0.1:4174/
```

## Data contract

- `data/latest.json`: PBKDF2 + AES-GCM encrypted latest complete Beijing calendar-day brief.
- `data/index.json`: lightweight publication metadata.
- Historical briefs remain in private MySQL and are not accumulated in Git.

The publishing workflow validates the plaintext brief locally, encrypts it with
`WISBURG_ACCESS_ANSWER` (falling back to `ACCESS_ANSWER` in the private repository), and
then verifies the deployed encrypted envelope's `briefDate`/`contentHash` before sending
the Feishu notification.
