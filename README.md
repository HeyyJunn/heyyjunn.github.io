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
into the Chirpy `_posts` collection. Velog's public GraphQL API is the authoritative
inventory and raw-Markdown source. The 20-item RSS feed is used only as a recent-post
health/sanity check, never as a complete inventory or body fallback.

The mapping is intentionally narrow:

- Velog series → Chirpy category
- Velog tags → not used; no `tags` front matter is generated and the Tags tab remains disabled

Post UUID is the stable identifier. New posts receive one fixed Markdown path; edits
to the title, body, series, slug, timestamp, or images update that same file. Source
deletions do not delete local posts automatically. Files managed from Velog treat
Velog as the source of truth, so manual edits to generated Markdown may be overwritten.

Images from the allowed Velog CDN are mirrored under
`assets/img/velog/<post-uuid>/`. Failed image downloads retain their remote URL, and
visible posts reuse verified local files. Hiding a post removes its deployable image
directory while preserving state metadata so an unhide can download it again.

Preview images use an explicit list-only priority: Velog `thumbnail`, then a
GitHub-only manual override, then no image. The first Markdown body image is never a
fallback. Resolved previews use custom `thumbnail:` front matter and the home-card
override only, so they are not inserted into post detail pages. Home cards keep text
on the left and use a small responsive thumbnail on the right. When Velog has no
thumbnail, open the post detail in `./blog ui` to upload one. The tracked source stays
under `.velog-sync/thumbnail-overrides/<post-uuid>/` and becomes a public asset only
while it is the active preview.

Home-card descriptions come directly from Velog GraphQL `short_description` and use
custom `preview_description:` front matter. Blank or whitespace-only source values
are omitted. The site does not derive a replacement from the Markdown body, and the
custom field is never rendered as an introduction on the post detail page.

Configure exclusions by UUID, exact normalized slug, or canonical URL in
the local manager. Number, slug, and canonical URL inputs are resolved against the
live inventory and persisted only as stable UUIDs in `.velog-sync/config.yml`.
`import_after` filters new imports only; it never prevents updates to already managed
posts.

The configured Velog account is read-only in the everyday manager because the UUID
ledger belongs to that source account. Changing accounts requires an explicit source
migration, not a settings edit. RSS is health/recent-inventory information only;
GraphQL raw Markdown is the sole canonical post body.

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
the Actions schedule and repository variables when automatic synchronization stops.

## 블로그 관리

가장 쉬운 관리 방법은 프로젝트 루트에서 다음 명령을 실행하는 것입니다.

```sh
./blog ui
```

필요한 Python 가상환경과 패키지를 자동으로 준비한 뒤 한국어 관리 화면을
`http://127.0.0.1:8765`에서 엽니다. 이 화면은 localhost에만 실행되며 실제
GitHub Pages 사이트에는 포함되지 않습니다.

터미널에서 관리하려면 `./blog help`로 전체 명령을 확인할 수 있습니다. 자주
사용하는 명령은 다음과 같습니다.

```sh
./blog list       # 게시물과 상태 보기
./blog dry-run    # 파일을 바꾸지 않고 변경 사항 확인
./blog sync       # 확인 후 로컬에 동기화
./blog publish    # 검사 후 허용된 관리 변경만 commit/push
./blog update     # 안전할 때만 origin/main을 fast-forward로 반영
./blog check      # 테스트, dry-run, 빌드, HTML 검사
./blog serve      # 127.0.0.1:4000에서 블로그 미리보기
```

게시물을 의도적으로 GitHub.io에서만 내릴 때 `_posts` 파일을 Finder나 VS Code로
직접 삭제하면 안 됩니다. Velog 원문이 남아 있으면 다음 동기화에서 복원됩니다.
반드시 `./blog hide <번호·UUID·slug>` 또는 관리 화면의 **GitHub에서 숨기기**를
사용하세요. 숨긴 글의 Velog 원문과 state의 이미지 metadata는 유지되지만,
GitHub Pages artifact에 노출되지 않도록 deployable 이미지 파일은 제거됩니다.
이는 Git history에서 과거 데이터를 완전히 삭제하는 privacy 기능은 아닙니다.

아직 GitHub에 가져오지 않을 글은 게시물 관리 화면이나
`./blog exclude add <번호·UUID·slug>`로 설정합니다. 실제 설정에는 제목이나
번호가 아닌 안정적인 Velog UUID가 저장됩니다. Velog 태그는 사용하지 않으며,
시리즈만 GitHub 카테고리로 동기화합니다.
