# Chirpy Starter

[![Gem Version](https://img.shields.io/gem/v/jekyll-theme-chirpy)][gem]&nbsp;
[![GitHub license](https://img.shields.io/github/license/cotes2020/chirpy-starter.svg?color=blue)][mit]

A minimal, ready-to-use template for creating a blog with the [**Chirpy**][chirpy] Jekyll theme. Get up and running in minutes with all critical files pre-configured.

## Why This Starter Exists

When installing Chirpy through [RubyGems.org][gem], Jekyll can only read a subset of theme files (`_data`, `_layouts`, `_includes`, `_sass`, `assets`) and limited `_config.yml` options from the gem. As a result, users cannot enjoy the full out-of-the-box experience that Chirpy offers.

To unlock all features, the following files must be present in your Jekyll site:

```shell
.
├── _config.yml
├── _plugins
├── _tabs
└── index.html
```

This starter bundles those files from the latest **Chirpy** release along with a [CD][CD] workflow, so you can start writing immediately.

## Usage

Check out the [theme's docs](https://github.com/cotes2020/jekyll-theme-chirpy/wiki).

## Contributing

This repository is automatically updated with new releases from the theme repository. If you encounter any issues or want to contribute to its improvement, please visit the [theme repository][chirpy] to provide feedback.

## License

This work is published under [MIT][mit] License.

[gem]: https://rubygems.org/gems/jekyll-theme-chirpy
[chirpy]: https://github.com/cotes2020/jekyll-theme-chirpy/
[CD]: https://en.wikipedia.org/wiki/Continuous_deployment
[mit]: https://github.com/cotes2020/chirpy-starter/blob/master/LICENSE

## Velog synchronization

This site synchronizes public posts from Velog [`@ilwha`](https://velog.io/@ilwha/posts)
into the Chirpy `_posts` collection. Velog's public GraphQL API is the primary source;
the 20-item RSS feed is used only as a recent-post sanity check and limited body
fallback, never as a complete inventory.

The mapping is intentionally narrow:

- Velog series → Chirpy category
- Velog tags → not used; no `tags` front matter is generated and the Tags tab remains disabled

Post UUID is the stable identifier. New posts receive one fixed Markdown path; edits
to the title, body, series, slug, timestamp, or images update that same file. Source
deletions do not delete local posts automatically. Files managed from Velog treat
Velog as the source of truth, so manual edits to generated Markdown may be overwritten.

Images from the allowed Velog CDN are mirrored under
`assets/img/velog/<post-uuid>/`. Failed image downloads retain their remote URL, and
existing mirrored images are never automatically deleted.

Configure exclusions by UUID, exact normalized slug, or canonical URL in
`.velog-sync/config.yml`. `import_after` filters new imports only; it never prevents
updates to already managed posts.

Run a read-only preview locally with:

```sh
python -m pip install -r requirements-velog-sync.txt
python scripts/sync_velog.py --dry-run
```

The existing Pages workflow offers manual `dry-run` and `apply` modes. Manual apply
works regardless of `VELOG_SYNC_ENABLED`. Scheduled apply runs at minutes 7, 22, 37,
and 52 only when the repository variable `VELOG_SYNC_ENABLED` is exactly `true`.
Automatic commits require both `BLOG_GIT_NAME` and `BLOG_GIT_EMAIL`; there is no
guessed or bot fallback identity. A complete source inventory and successful Jekyll
and htmlproofer validation are required before a changed tree is committed and
deployed. No-change runs create no commit and skip deployment.

GitHub may disable scheduled workflows after extended repository inactivity. Check
the Actions schedule and keep `VELOG_SYNC_ENABLED` disabled until the initial import
and production output have been reviewed.
