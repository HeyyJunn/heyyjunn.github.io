# PWA Service Worker removal migration

## Why this migration is staged

Chirpy 7.6 adds the following production script while `pwa.enabled` is truthy:

```liquid
?baseurl={{ site.baseurl | default: '' }}&register={{ site.pwa.cache.enabled }}
```

`_javascript/pwa/app.js` reads the value with
`URLSearchParams.get("register")` and tests it with `if (register)`.
Consequently, the three relevant YAML values behave as follows:

| YAML value | Generated query | JavaScript value | Result |
| --- | --- | --- | --- |
| `true` | `register=true` | `"true"` | register/cache worker |
| blank | `register=` | `""` | unregister registrations |
| `false` | `register=false` | `"false"` | **incorrectly registers** |

The literal `false` is therefore unsafe for `pwa.cache.enabled` in Chirpy
7.6. A blank value must be used during the removal migration.

Changing only that YAML value is not sufficient for every existing visitor.
The old cache-first worker may still return HTML containing `register=true`,
and Chirpy normally leaves a replacement worker waiting until the visitor
presses the Update button.

## Phase 1: active migration

The repository currently keeps `pwa.enabled: true` and sets
`pwa.cache.enabled` to a blank YAML value. New network-loaded pages therefore
execute Chirpy's unregister branch.

The site also overrides `/sw.min.js` with a migration worker that:

1. calls `skipWaiting()` during installation;
2. deletes caches whose names begin with `chirpy-`;
3. claims currently open site windows;
4. unregisters its own Service Worker registration;
5. navigates those windows once so they reload without the old cache.

It intentionally has no `fetch` listener and therefore does not add another
offline cache.

## Verification for Phase 1

After the deployment, verify all of the following:

- generated HTML contains `app.min.js?baseurl=&register=` and not
  `register=false`;
- `/assets/js/data/swconf.js` contains `purge: true`;
- `/sw.min.js` contains `skipWaiting`, cache deletion, and
  `registration.unregister()`;
- after visiting or reloading the site, the origin has no Service Worker
  registration and no `chirpy-*` Cache Storage entry;
- a second navigation does not show the New content available toast.

## Phase 2: optional full PWA disable

After Phase 1 has been deployed and verified, `pwa.enabled` may be changed to
`false`. This boolean is safe because Chirpy uses it in a Liquid conditional;
it is not passed to JavaScript through a URL query parameter. The PWA app
script, update notification markup, and web manifest link will then be omitted.

Keep the migration `/sw.min.js` endpoint even after disabling the PWA so a
long-dormant browser with the old registration can still update the endpoint,
delete its Chirpy cache, and unregister when it eventually returns.
