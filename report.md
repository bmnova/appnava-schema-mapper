# Flood-It! → AppNava schema mapping report

Source: `firebase-public-project.analytics_153293282.events_*`, profile range 20180801–20180803. Model: `claude-sonnet-5-5`.

> The LLM **proposed** this mapping. The SQL below was generated deterministically from it. Items marked ⚠️ need a human decision before the view is deployed.

## Summary

| Metric | Value |
|---|---|
| Events mapped | 17 / 33 (52%) |
| Rows mapped (profile, 3 days) | 37,464 / 150,000 (25.0%) |
| Rows mapped by the view (20180801) | 12,208 / 50,000 (24.4%) |
| Needs human review | 8 |
| Eval accuracy | 100% on 15 labeled events |
| Agent cost | $0.0892 (4 tool calls, 20,702 input / 6,444 output tokens) |

## Needs human review

- **`level_end_quickplay`** → unmapped (conf. 0.50): Level end with no param distinguishing complete vs fail; separate complete/fail events exist
- **`post_score`** → unmapped (conf. 0.50): Score posting; not clearly level_complete (separate level_complete event exists)
- **`select_content`** → `content_type=mode` → game_mode_select; `content_type=level` → feature_tap; `content_type=board` → feature_tap; `content_type=IAP` → feature_tap (conf. 0.60): content_type values mode/level/board/IAP; mode selections look like game mode choice, others generic taps; item_id semantics unverified
- **`level_end`** → unmapped (conf. 0.50): Level end with no outcome param; ambiguous between complete/fail
- **`level_up`** → unmapped (conf. 0.50): Level up may duplicate level_complete; unclear
- **`completed_5_levels`** → unmapped (conf. 0.60): Milestone, not a login streak or level_complete
- **`in_app_purchase`** → purchase (conf. 0.80): Real-money remove_ads purchase; value appears in micros (990000) so may need scaling
- **`dynamic_link_app_open`** → unmapped (conf. 0.60): Dynamic link open for invite campaign, not a push notification

## Mapping

| Source event | Rows (profile) | Target | Params | Conf. | Review | Reasoning |
|---|---:|---|---|---:|:---:|---|
| `screen_view` | 60,939 | unmapped |  | 0.90 |  | Generic SDK screen event, no target |
| `user_engagement` | 33,869 | unmapped |  | 0.95 |  | SDK system event |
| `level_start_quickplay` | 14,127 | level_start | game_mode ← 'quickplay' | 0.90 |  | Quickplay level start; board is size not level name |
| `level_end_quickplay` | 8,406 | unmapped |  | 0.50 | ⚠️ | Level end with no param distinguishing complete vs fail; separate complete/fail events exist |
| `post_score` | 5,865 | unmapped |  | 0.50 | ⚠️ | Score posting; not clearly level_complete (separate level_complete event exists) |
| `level_complete_quickplay` | 4,975 | level_complete | game_mode ← 'quickplay' | 0.85 |  | Quickplay level completion; value meaning unclear so score not mapped |
| `level_reset_quickplay` | 4,443 | level_retry | game_mode ← 'quickplay' | 0.80 |  | Reset = restart level in quickplay |
| `level_fail_quickplay` | 3,431 | level_fail | game_mode ← 'quickplay' | 0.90 |  | Quickplay level fail |
| `select_content` | 3,006 | `content_type=mode` → game_mode_select<br>`content_type=level` → feature_tap<br>`content_type=board` → feature_tap<br>`content_type=IAP` → feature_tap |  | 0.60 | ⚠️ | content_type values mode/level/board/IAP; mode selections look like game mode choice, others generic taps; item_id semantics unverified |
| `session_start` | 1,990 | session_start |  | 1.00 |  | Same name and meaning |
| `level_start` | 1,936 | level_start | level_name ← level_name | 0.90 |  | Level start with level_name |
| `level_end` | 1,325 | unmapped |  | 0.50 | ⚠️ | Level end with no outcome param; ambiguous between complete/fail |
| `level_retry` | 1,039 | level_retry | level_name ← level_name | 0.95 |  | Same meaning, level_name present |
| `level_up` | 890 | unmapped |  | 0.50 | ⚠️ | Level up may duplicate level_complete; unclear |
| `level_complete` | 866 | level_complete | level_name ← level_name | 0.90 |  | Level completion with level_name; value likely level not score |
| `level_retry_quickplay` | 733 | level_retry | game_mode ← 'quickplay' | 0.90 |  | Quickplay retry |
| `level_fail` | 435 | level_fail | level_name ← level_name | 0.90 |  | Level fail with level_name |
| `level_reset` | 270 | level_retry | level_name ← level_name | 0.75 |  | Reset = restart current level, has level_name |
| `firebase_campaign` | 266 | unmapped |  | 0.80 |  | Attribution event for invite-a-friend links, not a push click |
| `spend_virtual_currency` | 248 | unmapped |  | 0.90 |  | Virtual currency spend, no target |
| `use_extra_steps` | 211 | unmapped |  | 0.85 |  | In-game resource use, no target |
| `first_open` | 181 | unmapped |  | 0.85 |  | SDK install event, no target |
| `app_exception` | 96 | unmapped |  | 0.95 |  | Crash SDK event |
| `app_remove` | 86 | app_remove |  | 1.00 |  | Direct match |
| `app_update` | 82 | app_update | previous_app_version ← previous_app_version | 1.00 |  | Direct match with previous_app_version |
| `os_update` | 78 | unmapped |  | 0.90 |  | OS update, not app update |
| `no_more_extra_steps` | 65 | unmapped |  | 0.85 |  | Game-specific resource event, no target |
| `completed_5_levels` | 52 | unmapped |  | 0.60 | ⚠️ | Milestone, not a login streak or level_complete |
| `error` | 44 | unmapped |  | 0.90 |  | Error logging, no target |
| `ad_reward` | 29 | ad_reward_claim | reward_type ← type | 0.85 |  | Rewarded ad reward granted, type=Steps |
| `challenge_a_friend` | 14 | social_share |  | 0.85 |  | Challenging a friend matches social_share |
| `in_app_purchase` | 2 | purchase | product_id ← product_id, currency ← currency, value ← value | 0.80 | ⚠️ | Real-money remove_ads purchase; value appears in micros (990000) so may need scaling |
| `dynamic_link_app_open` | 1 | unmapped |  | 0.60 | ⚠️ | Dynamic link open for invite campaign, not a push notification |

## Unmapped events

Kept out of the view on purpose (SDK/system events or no matching target):

- `screen_view` (60,939 rows): Generic SDK screen event, no target
- `user_engagement` (33,869 rows): SDK system event
- `level_end_quickplay` (8,406 rows): Level end with no param distinguishing complete vs fail; separate complete/fail events exist
- `post_score` (5,865 rows): Score posting; not clearly level_complete (separate level_complete event exists)
- `level_end` (1,325 rows): Level end with no outcome param; ambiguous between complete/fail
- `level_up` (890 rows): Level up may duplicate level_complete; unclear
- `firebase_campaign` (266 rows): Attribution event for invite-a-friend links, not a push click
- `spend_virtual_currency` (248 rows): Virtual currency spend, no target
- `use_extra_steps` (211 rows): In-game resource use, no target
- `first_open` (181 rows): SDK install event, no target
- `app_exception` (96 rows): Crash SDK event
- `os_update` (78 rows): OS update, not app update
- `no_more_extra_steps` (65 rows): Game-specific resource event, no target
- `completed_5_levels` (52 rows): Milestone, not a login streak or level_complete
- `error` (44 rows): Error logging, no target
- `dynamic_link_app_open` (1 rows): Dynamic link open for invite campaign, not a push notification

## View validation on 20180801

| Target | Source | Rows |
|---|---|---:|
| ad_reward_claim | `ad_reward` | 7 |
| app_remove | `app_remove` | 24 |
| app_update | `app_update` | 17 |
| feature_tap | `select_content` | 196 |
| game_mode_select | `select_content` | 690 |
| level_complete | `level_complete_quickplay` | 1,697 |
| level_complete | `level_complete` | 320 |
| level_fail | `level_fail_quickplay` | 1,214 |
| level_fail | `level_fail` | 128 |
| level_retry | `level_reset_quickplay` | 1,298 |
| level_retry | `level_retry` | 379 |
| level_retry | `level_retry_quickplay` | 278 |
| level_retry | `level_reset` | 91 |
| level_start | `level_start_quickplay` | 4,587 |
| level_start | `level_start` | 667 |
| purchase | `in_app_purchase` | 1 |
| session_start | `session_start` | 608 |
| social_share | `challenge_a_friend` | 6 |

Mapped events that produced 0 rows: none.

## Eval against ground truth

Accuracy **100%** (15/15). Wrong answers caught by the review flag: 0/0. Flagged but correct: 6/6.

| Event | Expected | Predicted | | Flagged |
|---|---|---|:---:|:---:|
| `session_start` | session_start | session_start | ✅ |  |
| `level_start` | level_start | level_start | ✅ |  |
| `level_start_quickplay` | level_start | level_start | ✅ |  |
| `level_complete` | level_complete | level_complete | ✅ |  |
| `level_fail_quickplay` | level_fail | level_fail | ✅ |  |
| `level_end` | null | null | ✅ | ⚠️ |
| `level_end_quickplay` | null | null | ✅ | ⚠️ |
| `level_reset` | level_retry | level_retry | ✅ |  |
| `level_up` | null | null | ✅ | ⚠️ |
| `post_score` | null | null | ✅ | ⚠️ |
| `select_content` | feature_tap, game_mode_select | feature_tap, game_mode_select | ✅ | ⚠️ |
| `ad_reward` | ad_reward_claim | ad_reward_claim | ✅ |  |
| `in_app_purchase` | purchase | purchase | ✅ | ⚠️ |
| `challenge_a_friend` | social_share | social_share | ✅ |  |
| `screen_view` | null | null | ✅ |  |

Caveat: 15 labels, drafted by a separate Claude context (see `eval/ground_truth.yaml`); a larger human-labeled set would be a stronger test.

## Phase 2: SYNTHETIC Adapty subscription export

Same agent on `data/SYNTHETIC_adapty_events.csv` (30 hand-written rows, not real data). In this export `purchase` is sent for both a new subscription and a renewal, and no field says which. The expected behaviour is to flag it, not to pick one target blindly.

| Source event | Target | Conf. | Review | Reasoning |
|---|---|---:|:---:|---|
| `purchase` | purchase | 0.40 | ⚠️ | Adapty purchase on subscription products (20 rows/10 users, likely mix of first and renewal charges) with no param distinguishing start vs renew; no split invented, purchase is closest generic fit. |
| `subscription_expired` | subscription_expire | 0.95 |  | Name and semantics match subscription access ending. |
| `subscription_renewal_cancelled` | subscription_cancel | 0.93 |  | Auto-renew turned off matches subscription_cancel. |
| `subscription_renewal_reactivated` | unmapped | 0.80 | ⚠️ | Auto-renew re-enabled has no target in the schema; not a renew charge nor a new start, so left unmapped. |

Cost: $0.0204, 3 tool calls.

## Agent tool calls

1. `get_param_samples` {'event_name': 'select_content', 'param_key': 'content_type', 'limit': 10}
2. `get_param_samples` {'event_name': 'firebase_campaign', 'param_key': 'campaign', 'limit': 10}
3. `submit_mapping`  — rejected: mappings.8: Value error, select_content: use target_event OR split, not both
4. `submit_mapping` 

## Generated SQL

Written to `output/view.sql`; not deployed automatically.

```sql
CREATE OR REPLACE VIEW `YOUR_PROJECT.appnava_mapper.appnava_standard_events` AS
SELECT * FROM (
  SELECT
  PARSE_DATE('%Y%m%d', event_date) AS event_date,
  TIMESTAMP_MICROS(event_timestamp) AS event_ts,
  user_pseudo_id,
  event_name AS source_event,
  CASE
    WHEN event_name = 'level_start_quickplay' THEN 'level_start'
    WHEN event_name = 'level_complete_quickplay' THEN 'level_complete'
    WHEN event_name = 'level_reset_quickplay' THEN 'level_retry'
    WHEN event_name = 'level_fail_quickplay' THEN 'level_fail'
    WHEN event_name = 'select_content' AND (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'content_type') = 'mode' THEN 'game_mode_select'
    WHEN event_name = 'select_content' AND (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'content_type') = 'level' THEN 'feature_tap'
    WHEN event_name = 'select_content' AND (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'content_type') = 'board' THEN 'feature_tap'
    WHEN event_name = 'select_content' AND (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'content_type') = 'IAP' THEN 'feature_tap'
    WHEN event_name = 'session_start' THEN 'session_start'
    WHEN event_name = 'level_start' THEN 'level_start'
    WHEN event_name = 'level_retry' THEN 'level_retry'
    WHEN event_name = 'level_complete' THEN 'level_complete'
    WHEN event_name = 'level_retry_quickplay' THEN 'level_retry'
    WHEN event_name = 'level_fail' THEN 'level_fail'
    WHEN event_name = 'level_reset' THEN 'level_retry'
    WHEN event_name = 'app_remove' THEN 'app_remove'
    WHEN event_name = 'app_update' THEN 'app_update'
    WHEN event_name = 'ad_reward' THEN 'ad_reward_claim'
    WHEN event_name = 'challenge_a_friend' THEN 'social_share'
    WHEN event_name = 'in_app_purchase' THEN 'purchase'
  END AS target_event,
  CASE
    WHEN event_name = 'in_app_purchase' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'currency')
  END AS currency,
  CASE
    WHEN event_name = 'level_start_quickplay' THEN SAFE_CAST('quickplay' AS STRING)
    WHEN event_name = 'level_complete_quickplay' THEN SAFE_CAST('quickplay' AS STRING)
    WHEN event_name = 'level_reset_quickplay' THEN SAFE_CAST('quickplay' AS STRING)
    WHEN event_name = 'level_fail_quickplay' THEN SAFE_CAST('quickplay' AS STRING)
    WHEN event_name = 'level_retry_quickplay' THEN SAFE_CAST('quickplay' AS STRING)
  END AS game_mode,
  CASE
    WHEN event_name = 'level_start' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'level_name')
    WHEN event_name = 'level_retry' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'level_name')
    WHEN event_name = 'level_complete' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'level_name')
    WHEN event_name = 'level_fail' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'level_name')
    WHEN event_name = 'level_reset' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'level_name')
  END AS level_name,
  CASE
    WHEN event_name = 'app_update' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'previous_app_version')
  END AS previous_app_version,
  CASE
    WHEN event_name = 'in_app_purchase' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'product_id')
  END AS product_id,
  CASE
    WHEN event_name = 'ad_reward' THEN (SELECT COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING), CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) FROM UNNEST(event_params) AS p WHERE p.key = 'type')
  END AS reward_type,
  CASE
    WHEN event_name = 'in_app_purchase' THEN (SELECT COALESCE(p.value.double_value, p.value.float_value, CAST(p.value.int_value AS FLOAT64), SAFE_CAST(p.value.string_value AS FLOAT64)) FROM UNNEST(event_params) AS p WHERE p.key = 'value')
  END AS value
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE event_name IN ('level_start_quickplay', 'level_complete_quickplay', 'level_reset_quickplay', 'level_fail_quickplay', 'select_content', 'session_start', 'level_start', 'level_retry', 'level_complete', 'level_retry_quickplay', 'level_fail', 'level_reset', 'app_remove', 'app_update', 'ad_reward', 'challenge_a_friend', 'in_app_purchase')
)
WHERE target_event IS NOT NULL
```
