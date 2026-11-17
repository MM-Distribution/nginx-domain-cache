# Changelog

## 1.3.0 (2026-11-16)

- nginx-purge-spool: batches of up to 5,000 URLs, whole files only, repeated until the folders are empty. Before, a run
  stopped at 5,000 URLs and still deleted every file it had opened, so a big import's pages were silently not purged
  (found by a boundary review of mmd_nginx_purge).
- nginx-purge-spool: removes a site's leftover `.tmp-*` files older than an hour (plain files only, never links).
- Limits documented as the contract sites write to (256 KB per file). 15 tests; the 2 new ones fail on 1.2.0.

## 1.2.0 (2026-11-13)

- nginx-purge-url rewritten in Python on the shared nginx_purge.py: same options and output (checked against 1.1.0
  on the live cache), one scan per account folder for any number of URLs; URLs must have a real host name.
- New nginx-purge-spool + systemd units: sites drop changed-page lists in /var/spool/nginx-purge/<account>/, a
  watcher per account purges them within seconds, only on the account's own domains, logged, failures mailed.
- First tests (13).


## 1.1.0 (2026-10-30)

- New command `nginx-purge-url`: delete the cached copies of single pages (exact path with any query string, or `--prefix`), with `--dry-run`.

## 1.0.0 (2026-10-19)

- First version: `disable`, `enable`, `status`; domain check with suggestions; nginx config test with undo; waits for the reload to take effect.
