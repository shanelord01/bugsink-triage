# Bugsink API notes

Checked against Bugsink 2.6.0 and https://www.bugsink.com/docs/api/. Each server serves its own OpenAPI
schema, which is the authority for parameters: `GET <BUGSINK_URL>/api/canonical/0/schema/?format=json`
(Swagger UI at `/api/canonical/0/schema/swagger-ui/`). Read it again after a Bugsink upgrade.

Base: `<BUGSINK_URL>/api/canonical/0/`. Use this path. The `/api/0/` and `/api/<project-id>/` paths are for
Sentry compatibility (ingest and debug-file upload). Send `Authorization: Bearer <token>`.

## Tokens

Tokens are made in the Bugsink UI (Tokens menu), not through the API. From 2.6.0 a token has capabilities and
a scope. Project, team and "manage" capabilities need a global token. Tokens made before 2.6.0 keep full
access after an upgrade.

| Use | Capabilities needed |
|---|---|
| Reading (check.py, board.py) | `projects:read`, `issues:read`, `events:read` |
| Writing (act.py) | the read set, plus `issues:comment` and `issues:triage` |

Do not give an agent `issues:delete` unless you mean it. Revoke tokens you no longer use.

## Endpoints

| Purpose | Request |
|---|---|
| Projects | `GET /projects/` |
| Issues of a project | `GET /issues/?project=<id>&sort=last_seen&order=desc` (`sort`: `digest_order`, `digested_event_count`, `last_seen`) |
| Next page | follow the response's `next` URL; never build a cursor |
| One issue | `GET /issues/<uuid>/` |
| Events of an issue | `GET /events/?issue=<uuid>&order=desc` (`issue` is required) |
| One event, full payload | `GET /events/<event uuid>/` (`data` is the event as sent; `stacktrace_md` is the trace as Markdown) |
| Trace alone | `GET /events/<event uuid>/stacktrace/` |
| Comment | `POST /issue-comments/` with `{"issue": "<uuid>", "comment": "..."}` |
| Resolve | `POST /issues/<uuid>/resolve/` with `{}`; also `resolve-latest/`, `resolve-next/` |
| Reopen | `POST /issues/<uuid>/reopen/` |
| Mute, unmute | `POST /issues/<uuid>/mute/`, `unmute/` |
| Mute for a time | `POST .../mute-for/` with `{"period_name": "day", "nr_of_periods": 3}` |
| Mute until busy | `POST .../mute-until/` with `{"period_name": "hour", "nr_of_periods": 1, "gte_threshold": 10}` |

`period_name` is one of `year`, `month`, `week`, `day`, `hour`, `minute`. List pages are wrapped:
`{"next", "previous", "results": [...]}`. Useful issue fields: `friendly_id`, `calculated_type`,
`calculated_value`, `digested_event_count`, `first_seen`, `last_seen`, `is_resolved`, `is_muted`.
The Markdown in `stacktrace_md` may change between versions, so read it, do not parse it.

## Traps

Seen on Bugsink 2.6.0. Check the schema if your version differs.

- `GET /issues/` without `?project=` answers 400.
- `?is_resolved=false` and `?is_muted=` on the issue list are ignored: every issue comes back. Filter on each
  issue's `is_resolved` yourself, as the scripts do.
- `OPTIONS` on an issue lists only read and delete methods. That does not mean resolving is impossible: the
  triage actions are separate POST endpoints. Probe with `POST`.
- The comment field is `comment`, not `text`.
- Muting a resolved issue answers 400. Reopen it, then mute.
- The API root answers 500. That is not a connectivity problem.

## Unreadable traces

- **JavaScript**: source maps uploaded for the event's release (and dist) are applied. Missing maps show as
  "no sourcemap for debug_id" in the trace. Check that the build uploaded its maps for exactly that release.
- **Android Java and Kotlin**: with R8 or ProGuard on, frames show short class names. Bugsink 2.6.0 does not apply
  a mapping file to frames, so retrace by hand with Android's `retrace` tool and the `mapping.txt` from the same
  build. Check the map id in the mapping's header against the id in the frame's file name before trusting it.
- **Native iOS**: frames stay symbol-less unless debug symbols are uploaded and the server supports them.
- `sentry-cli` against Bugsink needs `SENTRY_URL` and `SENTRY_AUTH_TOKEN` from the same server, or it uploads
  to sentry.io and fails with "organization not found".
