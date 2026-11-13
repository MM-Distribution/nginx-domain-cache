# Changelog

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
