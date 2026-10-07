# Fetcher patterns by kind of site

Start every fetcher from the structure of `fetchers/llms_txt_fetcher.py`: argument parsing, a
`safe_join` that keeps paths inside the site folder, an atomic write, a scan of the existing copy
by content hash, the removal guard, `INDEX.md`, `CHANGES.txt`, and a non-zero exit on any failure.
What differs per kind of site is only how the list of pages is found and how each page is fetched.

## llms.txt site

Handled by the shipped fetcher; no new code. If the site lists pages that are HTML, not markdown,
try the same address with `.md` appended, or `index.md` for folder-style links. If neither gives
markdown, treat it as an HTML site.

## GitHub markdown repo (no token needed for a small public repo)

Settings on the sites entry: `repo` (`owner/name`), `branch`, `path` (the docs folder inside the
repo, e.g. `docs`).

1. List every file in one request with the repository's tree listing:
   `https://api.github.com/repos/<owner>/<name>/git/trees/<branch>?recursive=1`
   (JSON; `tree` is a list of `{path, type, sha}`). Anonymous calls are limited to 60 an hour, so
   use this one call and never one call per page. If the JSON says `truncated: true`, say so and
   fetch the `path` folder's own tree instead.
2. Keep entries with `type == "blob"`, a path under `path` and a name ending in `.md` (also `.mdx`
   if the docs use it; save those as `.md`).
3. Fetch each file from `https://raw.githubusercontent.com/<owner>/<name>/<branch>/<path>`. These
   are not rate limited the same way and need no token.
4. The mirror path is the repo path minus the `path` prefix. A folder's `README.md` or `index.md`
   becomes that folder's page. A top-level `index.md` is saved as `home.md`, because `INDEX.md`
   would overwrite it on a case-insensitive disk. Page titles come from the first `# ` heading; fall back to the file name.
5. The tree entry's blob `sha` changes when the file changes, but compare the content hash of what
   you downloaded, as the shipped fetcher does, so the summary is the same for every kind of site.
6. Skip generated or non-documentation files (changelogs of a thousand lines are fine, images are
   not). Say what you skipped.
7. A private repo or a rate-limit error (HTTP 403 or 429) fails the run plainly; do not ask the user for a token.

## HTML site (last resort)

Only when there is no llms.txt and no markdown source.

1. Find the page list: a `sitemap.xml` (parse `<loc>` entries, stay on the site's host and under
   the docs path) or the navigation links on the start page. Cap the crawl (a few hundred pages)
   and remember which addresses you have seen.
2. Fetch each page and keep the main content only (the `<main>` or `<article>` element, else the
   `<body>`). Drop script, style, nav, header, footer and aside.
3. Convert to markdown with the standard library only: parse with `html.parser`, and write headings
   as `#` lines, list items as `- `, code blocks as fences, and links as `[text](url)`. A
   plain, slightly rough conversion is fine; a page of raw tags is not.
4. Respect `robots.txt` (use `urllib.robotparser`) and keep the delay at one second or more.
5. If the pages are drawn by JavaScript and the fetched HTML has no text, stop and say the site
   cannot be mirrored this way.
