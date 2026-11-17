"""Find and delete cPanel ea-nginx page-cache copies of given URLs. Shared by nginx-purge-url (one person, a few
URLs) and nginx-purge-spool (sites dropping lists of changed pages), so the matching rule lives in one place.

The rule: a URL matches every cached copy of that path for the host with or without "www.", over http or https, with
or without a query string (prefix=True: every path that starts with it). Copies are found by the "KEY: <url>" line
nginx writes near the start of each cache file under <cache root>/<account>/, and only files under that folder are
ever deleted. Each account folder is read once per call, however many URLs it gets (a price import can change
hundreds of pages at once).
"""
import os
import re
from dataclasses import dataclass, field

CACHE_ROOT = "/var/cache/ea-nginx/proxy"
DOMAINS_FILE = "/etc/userdatadomains"
KEY_SCAN_BYTES = 4096  # the KEY line sits ~340 bytes in (checked 2026-11-13 on 1,078 files); fall back to the whole file

# Copied by mmd_nginx_purge (MM-Distribution/mmd_nginx_purge, mmd_nginx_purge_spool_url() in mmd_nginx_purge.spool.inc):
# change both together, or a site writes lines this refuses (logged only here).
URL_RE = re.compile(r"^(https?://)?([A-Za-z0-9.-]+\.[A-Za-z]{2,})(/[^?#\s]*)?([?][^#\s]*)?$")


class BadUrl(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    url: str
    bare_host: str  # lower case, without "www."
    path: str
    prefix: bool

    def matches(self, key: str) -> bool:
        m = re.match(r"^https?://(?:www\.)?([^/?#]+)(/[^?#]*)?([?].*)?$", key)
        if not m or m.group(1).lower() != self.bare_host:
            return False
        path = m.group(2) or "/"
        return path.startswith(self.path) if self.prefix else path == self.path


def parse(url: str, prefix: bool = False) -> Target:
    m = URL_RE.match(url.strip())
    if not m:
        raise BadUrl(f"not a URL: {url}")
    host = m.group(2).lower()
    return Target(url.strip(), host[4:] if host.startswith("www.") else host, m.group(3) or "/", prefix)


def domain_accounts(domains_file: str = DOMAINS_FILE) -> dict:
    """cPanel's domain -> account map (every main, addon, sub and parked domain on the server)."""
    accounts = {}
    with open(domains_file) as f:
        for line in f:
            domain, sep, rest = line.partition(": ")
            if sep:
                accounts[domain.strip().lower()] = rest.split("==", 1)[0].strip()
    return accounts


def account_of(target: Target, accounts: dict):
    return accounts.get(target.bare_host) or accounts.get("www." + target.bare_host)


def read_key(path: str):
    """The cache key of one cache file, or None (no KEY line, or the file is gone: nginx's cache manager evicts files
    at any moment, between the folder listing and this read)."""
    try:
        f = open(path, "rb")
    except FileNotFoundError:
        return None
    with f:
        head = f.read(KEY_SCAN_BYTES)
        i = head.find(b"\nKEY: ")
        if i < 0:
            head += f.read()
            i = head.find(b"\nKEY: ")
            if i < 0:
                return None
    line = head[i + 6:].split(b"\n", 1)[0]
    return line.decode("utf-8", "replace").rstrip("\r")


@dataclass
class Result:
    deleted: list = field(default_factory=list)      # cache keys deleted (or that would be, on a dry run)
    not_cached: list = field(default_factory=list)   # URLs with no cached copy
    unknown: list = field(default_factory=list)      # URLs whose domain isn't on this server


def purge(targets: list, dry_run: bool = False, cache_root: str = CACHE_ROOT, accounts: dict = None) -> Result:
    accounts = domain_accounts() if accounts is None else accounts
    result = Result()
    by_account = {}
    for t in targets:
        acct = account_of(t, accounts)
        if acct is None:
            result.unknown.append(t.url)
        else:
            by_account.setdefault(acct, []).append(t)
    for acct, wanted in sorted(by_account.items()):
        folder = os.path.realpath(os.path.join(cache_root, acct))
        hit = set()
        if os.path.isdir(folder):
            for root, _, files in os.walk(folder):
                for name in files:
                    path = os.path.join(root, name)
                    if os.path.islink(path) or not os.path.realpath(path).startswith(folder + os.sep):
                        continue  # never follow a link out of the account's cache folder
                    key = read_key(path)
                    matching = [t for t in wanted if key and t.matches(key)]
                    if not matching:
                        continue
                    hit.update(t.url for t in matching)
                    if not dry_run:
                        try:
                            os.unlink(path)
                        except FileNotFoundError:
                            pass  # evicted by nginx meanwhile: the copy is gone either way
                    result.deleted.append(key)
        result.not_cached.extend(t.url for t in wanted if t.url not in hit)
    return result
