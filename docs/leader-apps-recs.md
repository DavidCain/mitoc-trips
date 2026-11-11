# Design proposal — in-app leader rating upgrade flow (data model)

## Problem && objective

The leader rating upgrade flow is spread across three places:

1. **mitoc-trips** — trip feedback and the Winter School initial application.
2. **Upgrade request google form**
3. **Recommandation google form**

The safety committee reviews them by juggling between mitoc-trips and multiple crowded spreadsheets. It is tedious and impractical, especially during crunch time (weekly udpates during Winter School and School of Rock).

The goal of the proposal is to migrate all applications and recommendations into mitoc-trips, in order to offer a single view of an applicant's application, which would expose the application, recommendations, and feedback collected on trip as participant. 


## Constraints

- **Questions evolve year over year.** The form needs to be versioned; a submission must always render against the schema it was filled with.
- **Modularity.** Some questions are common to every rating; others are specific to a target rating.
- **Application/recommendation can target multiple ratings at once.** (e.g. a single recommendation for Sport and Trad for an aspiring climbing leader)


## Data Model Proposal

### `FormVersion`

A frozen, versioned schema snapshot describing what a form asks. **One
version per (kind, activity)** — the rating-specific chunks live inside the
schema, as sections tagged with the ratings they apply to.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | enum | `application` \| `recommendation` |
| `activity` | enum | reuses the existing activity enum (climbing, winter_school, …) |
| `version` | int | auto-incremented per (kind, activity) |
| `schema` | `JSONField` | ordered sections → ordered questions. See below. |
| `status` | enum | `draft` \| `published` \| `archived`. `schema` is mutable only while `draft` |
| `published_at` | datetime, nullable | |
| `created_by` | FK → Participant | |
| `created_at` | datetime | |

Example `schema` — Winter School application, three target ratings available:

```json
{
  "sections": [
    { "title": "General skills",
      "appliesTo": "*",
      "questions": [
        { "persistentId": "wfa-current", "type": "yes_no",
          "prompt": "Do you hold a current WFA?", "required": true }
      ]
    },
    { "title": "B rating",
      "appliesTo": ["B"],
      "questions": [
        { "persistentId": "winter-b-trips", "type": "long_text",
          "prompt": "Describe your most relevant B-terrain trips in the past 2 years." }
      ]
    },
    { "title": "coC rating",
      "appliesTo": ["coC"],
      "questions": [ ... ]
    },
    { "title": "Ski - coS rating",
      "appliesTo": ["coS"],
      "questions": [ ... ]
    }
  ]
}
```

**Section-level `appliesTo`:** either `"*"` (always shown) or a list of rating
codes.

**Supported question `type`s:** `yes_no`, `text`, `long_text`,
`integer`, `single_choice` (with `options`), `multi_choice` (with
`options`), `grid` (with `rows`, `columns`).
Grid is meant to handle the case where a recommender has to rate multiple skills on a scale from 1 to 4. 

**persistentId** allows to track the lineage of a question between different editions of the form. 


### `UpgradeRequest`

The formal application itself and the case folder around it — one entity.
Filing an application *is* creating an `UpgradeRequest`.

| Field | Type | Notes |
| --- | --- | --- |
| `applicant` | FK → Participant | the person filing the request |
| `activity` | enum | |
| `form_version` | FK → `FormVersion` (PROTECT) | the `application`-kind version the applicant filled in. Invariant enforced in `save()`: `form_version.kind == 'application'` and `form_version.activity == self.activity` |
| `answers` | `JSONField` | frozen at submission, keyed by question `persistentId` |
| `submitted_at` | datetime | when the applicant filed |
| `closed_at` | datetime, nullable | when every requested rating has reached a terminal status |

Requested ratings — and their individual outcomes — live in a child table
(next model).

### `UpgradeRequestRating`

One row per rating the applicant is requesting on this request. Allows the
committee to decide each rating independently.

| Field | Type | Notes |
| --- | --- | --- |
| `request` | FK → `UpgradeRequest` | |
| `rating` | `CharField` | free-text, e.g. `"B"`, `"coC"`, `"coS"`. Matches `BaseRating.rating` convention |
| `status` | enum | `pending`, `deferred`, `approved`, `rejected`, `withdrawn` |
| `outcome_rating` | FK → `LeaderRating`, nullable | populated when the committee grants this specific rating |
| `decided_at` | datetime, nullable | |

Unique constraint on `(request, rating)`.

**Status meanings.**

- `pending` — Needs review by the safety committee
- `deferred` — the committee has reviewed and chosen to ask for more experience and/or recommandations
- `approved`, `rejected`, `withdrawn` — terminal.

Only terminal statuses count toward `UpgradeRequest.closed_at` — a
`deferred` row keeps the request open.


### `RecommendationFormSubmission`

A letter of support from a peer leader.

| Field | Type | Notes |
| --- | --- | --- |
| `form_version` | FK → `FormVersion` (PROTECT) | invariant: `form_version.kind == 'recommendation'` |
| `activity` | enum | denormalized from `form_version.activity` at save time. Immutable. Lets review queries filter without joining `FormVersion` and anchors the index below across version bumps |
| `author` | FK → Participant | the leader writing the recommendation |
| `applicant` | FK → Participant |  The person being endorsed |
| `target_ratings` | `ArrayField[CharField]` | the subset of ratings the recommender is willing to speak to (they may vouch for `B` and `coC` but not `coS`) |
| `answers` | `JSONField` | keyed by question `persistentId`. Keys from sections not addressed by `target_ratings` simply aren't present |
| `submitted_at` | datetime | |


**Index.** `(applicant, activity, submitted_at DESC)`. Supports "every
recommendation ever written about this applicant on this activity,
newest first


### `UpgradeComment` (nice to have)

Short free-text notes strictly attached to an open `UpgradeRequest`.
Covers three use cases on one table:

- An applicant adds an addendum to their own application ("Gained more
  experience with X on trip Y, asked leader Z for a new rec").
- A committee member documents the committee's position at a point in
  time ("Seems familiar with X, but needs to demonstrate Y before the
  rating").
- A committee member documents the committee's position at a point in
  time ("Seems familiar with X, but needs to demonstrate Y before the
  rating").

| Field | Type | Notes |
| --- | --- | --- |
| `upgrade_request` | FK → `UpgradeRequest` (CASCADE) | **required** |
| `author` | FK → Participant | who wrote the comment |
| `body` | `TextField` | the free-text note |
| `visible_to_applicant` | `BooleanField` | default `False`. Set at creation and immutable thereafter . Lets committee members elevate a note to a "message to the applicant" — useful for communicating a decision or asking for more info.
| `created_at` | datetime | |


**Visibility rules.**

- The committee always sees every comment on a request they're reviewing.
- An applicant-authored comment is always visible to the applicant
  (they wrote it) — the `visible_to_applicant` flag is effectively
  ignored for self-authored comments.
- For comments authored by anyone else, the applicant sees them iff
  `visible_to_applicant == True`.