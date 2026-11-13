# nginx-domain-cache

Turn cPanel's nginx page cache off for a single domain. WHM's NGINX Manager
only switches the cache on or off for a whole account, so an account with a
live site and a test site has to choose one setting for both. This script
leaves the account cached and opts single domains out.

## Use (root)

```
nginx-domain-cache disable dev.example.com   # cache off for this domain
nginx-domain-cache enable dev.example.com    # back to the account's setting
nginx-domain-cache status dev.example.com    # what applies to this domain
nginx-domain-cache status                    # every domain turned off by this script
```

- A leading `www.` is ignored.
- A domain that isn't in cPanel is refused, with a list of similar names
  (`/etc/userdatadomains`) in case of a typo.
- Running `disable` twice, or `enable` on a domain that isn't disabled,
  changes nothing.
- `status` also lists overrides whose domain has since been removed from
  cPanel; delete those files by hand.

## How it works

ea-nginx (cPanel's nginx) writes one `server` block per domain into
`/etc/nginx/conf.d/users/<account>.conf`. Each block ends by including
`/etc/nginx/conf.d/users/<account>/<folder>/*.conf`, a folder cPanel leaves
alone when it rebuilds the config. The folder is named after the domain; for
an addon domain it is named after its subdomain twin (for example
`example.com.main.tld`). The script reads the folder name from the server
block instead of guessing it.

`disable` writes `nginx-domain-cache.conf` into that folder:

```nginx
set $CPANEL_PROXY_CACHE off;
set $CPANEL_SKIP_PROXY_CACHING 1;
```

These are the variables cPanel's own `proxy_cache`, `proxy_no_cache` and
`proxy_cache_bypass` lines use. They come after cPanel's own settings for the
domain, so they take precedence. `enable` deletes the file, so the domain
goes back to the account's setting.

Every change is followed by `nginx -t`. If the test fails, the change is undone
and nginx is not reloaded. After a good test the script reloads nginx and waits
until the new workers are taking connections (about a second), so the change is
live when the command returns.

The file only turns caching off. There is no per-domain "on": with the account's
cache off, cPanel writes no cache lines at all, so there is nothing to switch
back on. Hence: file present = off, no file = account setting.

## Good to know

- cPanel already skips the cache for domains protected with its Password
  Protected Directories (its config says "has basic auth, so disable cache"),
  including protection set on a parent folder of the document root. `status`
  says so for such domains; `disable` is still useful if that protection might
  be removed later.
- Pages cached before `disable` are no longer served for that domain, but stay
  in `/var/cache/ea-nginx/proxy/<account>/` until they expire (60 minutes by
  default). After `enable`, the cache refills as pages are requested.
- Account settings: `/var/cpanel/userdata/<account>/nginx-cache.json`, else
  the server default `/etc/nginx/ea-nginx/cache.json`.

## Install

```
install -m 755 nginx-domain-cache /usr/local/sbin/
```

Tested on AlmaLinux 8, cPanel ea-nginx 1.31.6 in reverse-proxy mode.

## nginx-purge-url

Deletes the cached copies of single pages (not a whole domain), so the next request goes to the site. Useful after
a page's status changes (published, unpublished, 403 to 410) on a site whose pages nginx caches.

```
nginx-purge-url [-n] [--prefix] <url> [<url> ...]
```

- A URL matches its exact path with or without a query string, over http and https, with and without `www.`.
- `-n` / `--dry-run` lists what would be deleted. `--prefix` matches every path starting with the URL's path.
- Options apply to every URL on the command line: run `--prefix` purges on their own.
- Copies are found by the `KEY:` line in each file under `/var/cache/ea-nginx/proxy/<account>/` (account from
  `/etc/userdatadomains`); nothing outside that folder is touched. One URL can have several copies (one per
  `Vary` variant).

Since 1.2.0 it is Python (`/usr/bin/python3.12`) on the shared `nginx_purge.py`, same options and output, and reads
each account's cache folder once however many URLs it gets (300 URLs on a 67 MB cache: 0.4 s; the bash 1.1.0 took
about 1 s per 20).

Install: `install -m 644 nginx_purge.py /usr/local/lib/nginx-purge/` and `install -m 755 nginx-purge-url /usr/local/sbin/`.

## nginx-purge-spool (sites ask for purges)

Sites can't delete nginx's cache files themselves (they run as their own account; the cache belongs to nginx). A site
that wants its changed pages purged at once writes their URLs, one per line, to a temporary file in its own folder
`/var/spool/nginx-purge/<account>/` (owner the account, 700) and renames it to `*.urls`. A systemd watcher per
account (`nginx-purge-spool@<account>.path`, inotify: nothing polls) starts `nginx-purge-spool.service`, which:

- waits 2 s (a save that changes several pages finishes dropping its lists), then reads every `*.urls` file;
- accepts a file only if it is a plain file (no links) owned by that account, at most 256 KB;
- purges a URL only if its domain belongs to that account (`/etc/userdatadomains`), so a site can't clear another
  site's pages; refused lines are logged with the reason;
- purges all URLs in one batch (`nginx_purge.py`), deletes the files, and logs one line per run to
  `/var/log/nginx-purge-spool.log`;
- on failure, `nginx-purge-spool-failed.service` mails root the service status (`sendmail -t`).

Which accounts may: `/etc/nginx-purge/accounts` (one per line). After editing it, `nginx-purge-spool --setup` makes
the folders and enables or disables the watchers. Units: `systemd/` (install to `/etc/systemd/system/`, then
`systemctl daemon-reload`).

Tests: `python3.12 -m unittest discover -s tests -t .` (as root: the spool tests need real file ownership).

