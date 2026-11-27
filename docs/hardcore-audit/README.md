# Rai hardcore audit

## v1.0.0 baseline

The audit covers new messages handled by the Spanish server’s personal and forced
hardcore workflow in both target-language directions. When both modes apply,
the audit records the forced mode, which takes precedence during enforcement.
The existing preprocessing, English/Spanish classifier, confidence thresholds,
role rules, and exemptions define the baseline.

Counts are stored by UTC day, workflow version, target language, enforcement mode,
and corpus identity. Corpus identity includes the selected directory and a SHA-256
fingerprint of the training text actually supplied to the model. Report cleaned,
fallback, and unknown corpus identities separately. An already-loaded model
without a fingerprint appears as `unknown` unless its startup selection has
been verified and attributed in the private `corpus-attribution.json` file.
Labels ending in `:startup-log` record the selected directory from the startup
log. The file applies to the identified process, and a model fingerprint takes
precedence whenever available.

| Outcome | Meaning |
| --- | --- |
| `kept` | The classifier returned a language and hardcore kept the message. |
| `abstained` | The classifier ran and returned no language. Included in the kept total. |
| `exempt` | The classifier ran, then the enforcement rule exempted the message, such as the `holi` exemption. Reported separately from classifier keeps. |
| `deleted` | The hardcore delete call succeeded. |
| `delete_raced` | Discord reported that the message was already gone. |
| `delete_failed` | The deletion request failed, for example because Discord denied it or the connection failed. |

The evaluated total is the sum of these outcomes. Messages that bypassed the
classifier or had no detector result because the detector was unavailable or
failed are outside that total. The audit excludes channels exempted from the
existing deletion log, including threads under those channels.

## Read the local audit

The message cog writes to `local/hardcore-audit/audit.sqlite` under the checkout.
The directory and database are private to the bot’s OS account. From the checkout
root, run these commands with the bot’s Python interpreter:

```bash
python -m cogs.utils.hardcore_audit summary
python -m cogs.utils.hardcore_audit deletions
```

Both commands emit JSON lines. Deletion records include the original text, the
exact input sent to the classifier, and decision metadata. Kept messages contribute
counts only. The bot purges deletion records at startup and hourly thereafter
once they reach 90 days. Reading deletions also purges expired records. Daily
aggregates persist independently. Treat deletion command output as private
message data subject to the same retention window.

## Live results

| Workflow | Hypothesis | Observed wrongful-deletion share |
| --- | --- | --- |
| v1.0.0 | 5% | Pending review data |

A review assigns two labels:

- **Language composition** is target-only, non-target-only, mixed, or unclear.
- **Policy verdict** is allowed, disallowed, or unresolved. Judge mixed messages
  against the agreed policy. Use unresolved when the policy or evidence cannot
  settle the case. Infer language from the text and leave the author’s intent
  unspecified.

For each reporting window and version, target, mode, and corpus grouping, show
the confirmed deletion count, reviewed count, unresolved count, and unreviewed
count. Divide allowed verdicts by allowed plus disallowed verdicts to get the
wrongful-deletion share. With zero resolved verdicts, report the share as pending.
Kept counts measure decision volume. Estimating errors among keeps would require
labels for a representative sample of those messages.

Record future live results only as aggregates. Bump the workflow version when a
release changes preprocessing, classifier thresholds, training data, or
enforcement in a way that can affect outcomes. Record the loaded corpus for each
version so fallback periods remain visible. The
[offline language benchmark](../language_detection_benchmark.md) measures
classifier performance independently.
