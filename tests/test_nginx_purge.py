import importlib.machinery
import importlib.util
import os
import pwd
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, HERE)
import nginx_purge as np  # noqa: E402

loader = importlib.machinery.SourceFileLoader("spool", os.path.join(HERE, "nginx-purge-spool"))
spec = importlib.util.spec_from_loader("spool", loader)
spool = importlib.util.module_from_spec(spec)
loader.exec_module(spool)

ACCOUNTS = {"shop.com": "acct1", "www.shop.com": "acct1", "other.com": "acct2"}


def cache_file(folder, key, pad=330, name=None):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name or f"f{abs(hash((key, pad)))}")
    with open(path, "wb") as f:
        f.write(b"\x00" * pad + b"\nKEY: " + key.encode() + b"\nHTTP/1.1 200 OK\n\n<html>")
    return path


class MatchTest(unittest.TestCase):
    TABLE = [  # (url, prefix, cache key, matches?)
        ("https://shop.com/products/x", False, "https://www.shop.com/products/x", True),
        ("https://www.shop.com/products/x", False, "http://shop.com/products/x?page=2", True),
        ("shop.com/products/x", False, "https://shop.com/products/x", True),
        ("https://shop.com/products/x", False, "https://shop.com/products/xy", False),
        ("https://shop.com/products/x", False, "https://other.com/products/x", False),
        ("https://shop.com/", False, "https://shop.com/", True),
        ("https://shop.com", False, "https://shop.com/", True),
        ("https://shop.com/blog/", True, "https://shop.com/blog/post-1?x=1", True),
        ("https://shop.com/blog/", True, "https://shop.com/news/", False),
    ]

    def test_table(self):
        for url, prefix, key, want in self.TABLE:
            with self.subTest(url=url, key=key):
                self.assertEqual(np.parse(url, prefix).matches(key), want)

    def test_bad_url(self):
        with self.assertRaises(np.BadUrl):
            np.parse("https://shop.com/a#frag b c")


class PurgeTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.a1 = os.path.join(self.root, "acct1")
        self.p = cache_file(self.a1, "https://www.shop.com/products/x")
        self.q = cache_file(self.a1, "https://www.shop.com/products/x?page=2")
        self.other = cache_file(self.a1, "https://www.shop.com/products/y")

    def test_deletes_all_copies_of_the_page_only(self):
        r = np.purge([np.parse("https://shop.com/products/x")], cache_root=self.root, accounts=ACCOUNTS)
        self.assertEqual(sorted(r.deleted), ["https://www.shop.com/products/x", "https://www.shop.com/products/x?page=2"])
        self.assertFalse(os.path.exists(self.p) or os.path.exists(self.q))
        self.assertTrue(os.path.exists(self.other))

    def test_dry_run_deletes_nothing(self):
        r = np.purge([np.parse("https://shop.com/products/x")], dry_run=True, cache_root=self.root, accounts=ACCOUNTS)
        self.assertEqual(len(r.deleted), 2)
        self.assertTrue(os.path.exists(self.p))

    def test_unknown_domain_and_not_cached(self):
        r = np.purge([np.parse("https://nowhere.com/a"), np.parse("https://shop.com/never")], cache_root=self.root,
                     accounts=ACCOUNTS)
        self.assertEqual((r.unknown, r.not_cached), (["https://nowhere.com/a"], ["https://shop.com/never"]))

    def test_link_out_of_the_cache_folder_is_never_followed(self):
        outside = cache_file(os.path.join(self.root, "elsewhere"), "https://www.shop.com/products/x")
        os.symlink(outside, os.path.join(self.a1, "link"))
        np.purge([np.parse("https://shop.com/products/x")], cache_root=self.root, accounts=ACCOUNTS)
        self.assertTrue(os.path.exists(outside))

    def test_key_found_beyond_the_first_4k(self):
        far = cache_file(self.a1, "https://www.shop.com/far", pad=9000)
        self.assertEqual(np.read_key(far), "https://www.shop.com/far")

    def test_domain_file(self):
        f = os.path.join(self.root, "userdatadomains")
        with open(f, "w") as fh:
            fh.write("shop.com: acct1==acct1==main==shop.com==/home/acct1/public_html==1.2.3.4:81====0==ea-php84\n")
        self.assertEqual(np.domain_accounts(f), {"shop.com": "acct1"})


@unittest.skipUnless(os.geteuid() == 0, "needs root for file ownership")
class SpoolTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.spool = os.path.join(self.root, "spool")
        self.cache = os.path.join(self.root, "cache")
        self.acct = "nobody"  # a real account for ownership checks
        self.uid = pwd.getpwnam(self.acct).pw_uid
        self.accounts = {"shop.com": "nobody", "other.com": "someoneelse"}
        os.makedirs(os.path.join(self.spool, self.acct))
        self.accounts_file = os.path.join(self.root, "accounts")
        with open(self.accounts_file, "w") as f:
            f.write("nobody  # test\n")
        self.log = os.path.join(self.root, "log")
        self.page = cache_file(os.path.join(self.cache, "nobody"), "https://www.shop.com/products/x")
        self.home = cache_file(os.path.join(self.cache, "nobody"), "https://www.shop.com/")

    def drop(self, text, name="a.urls", owner=None):
        path = os.path.join(self.spool, self.acct, name)
        with open(path, "w") as f:
            f.write(text)
        os.chown(path, self.uid if owner is None else owner, -1)
        return path

    def run_spool(self):
        return spool.run(self.spool, self.accounts_file, self.log, self.cache, self.accounts)

    def test_own_pages_purged_other_domains_refused_file_removed(self):
        f = self.drop("https://shop.com/products/x\nhttps://other.com/\nnot a url at all\n\nhttps://shop.com/\n")
        r = self.run_spool()
        self.assertEqual(sorted(r.deleted), ["https://www.shop.com/", "https://www.shop.com/products/x"])
        self.assertFalse(os.path.exists(f))
        log = open(self.log).read()
        self.assertIn("other.com is not nobody's domain", log)
        self.assertIn("not a URL", log)
        self.assertIn("files 1, urls 2, cached copies deleted 2", log)

    def test_file_not_owned_by_the_account_is_refused(self):
        self.drop("https://shop.com/products/x\n", owner=0)
        r = self.run_spool()
        self.assertEqual(r.deleted, [])
        self.assertTrue(os.path.exists(self.page))
        self.assertIn("not owned by the account", open(self.log).read())

    def test_symlink_is_refused(self):
        target = os.path.join(self.root, "secret")
        with open(target, "w") as f:
            f.write("https://shop.com/products/x\n")
        os.symlink(target, os.path.join(self.spool, self.acct, "b.urls"))
        self.run_spool()
        self.assertTrue(os.path.exists(self.page))
        self.assertIn("refused", open(self.log).read())

    def test_unfinished_file_is_left_alone(self):
        tmp = self.drop("https://shop.com/products/x\n", name="a.tmp")
        self.run_spool()
        self.assertTrue(os.path.exists(tmp) and os.path.exists(self.page))

    def test_account_not_listed_is_ignored(self):
        with open(self.accounts_file, "w") as f:
            f.write("# nobody removed\n")
        f = self.drop("https://shop.com/products/x\n")
        self.run_spool()
        self.assertTrue(os.path.exists(f) and os.path.exists(self.page))


if __name__ == "__main__":
    unittest.main()
