# Ideas

Not planned yet; written down to decide later.

## Wildcard domains (`*.sandbox.example.com`)

Test sites are often grouped as subdomains of one name (`a.sandbox.example.com`,
`b.sandbox.example.com`). Turning the cache off for each by hand is easy to forget when a new one is
added. A pattern could cover them all.

Points to settle:

- **The pattern means subdomains only.** The parent (`sandbox.example.com`) may share a server block
  with the live site (an alias), so disabling it would also stop caching the live site.
  `*.sandbox.example.com` should match `a.sandbox.example.com` but not `sandbox.example.com`.
- **Existing vs. future subdomains.** nginx has no per-pattern switch: cPanel writes one server block
  per domain, and the override file goes into each block's folder. Two ways to do it:
  1. *Expand now:* `disable '*.sandbox.example.com'` disables every current match. Simple, but a
     subdomain added later stays cached until the command is run again.
  2. *Remember the pattern:* also save it (e.g. `/etc/nginx-domain-cache/patterns`), add an `apply`
     command that disables every matching domain not yet disabled, and run `apply` from a cPanel hook
     when a subdomain or addon domain is created, so new ones start uncached. `status` lists patterns
     and the domains they cover; `enable '*.sandbox.example.com'` removes the pattern and its
     overrides. Preferred, as nobody has to remember.
- **Testing:** the current matches plus a throwaway subdomain created and removed for the hook.
