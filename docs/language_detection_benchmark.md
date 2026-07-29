# Language detection corpus and benchmark

Rai's language benchmark is an internal, offline module. It does not import a
Discord cog, contact an API, install packages, or use a paid service.

## Build the cleaned corpus

The builder validates both audit tables against the exact source filename,
one-based line number, character count, and text before it writes anything:

```bash
python3 -m cogs.utils.language_corpus build \
  --output-dir cogs/utils/corpus/audit_cleaned_2026_07_27
```

The four original CSV files in `cogs/utils` are read-only inputs. Retained
rows are copied byte-for-byte into the derived directory. By default, the
builder also removes unaudited occurrences of an audited message when the
exact same text occurs in another corpus for the same expected language.
`manifest.json` records every removed source row, its reason, row counts, and
input/output SHA-256 hashes.

The builder refuses to replace an existing output directory unless
`--overwrite` is explicitly supplied.

Production prefers the four files in
`cogs/utils/corpus/audit_cleaned_2026_07_27`. Until all four are deployed
there, it falls back as a unit to the existing files in `cogs/utils`; it never
mixes cleaned and original files. A partially deployed cleaned directory emits
a warning. Corpus files are ignored by Git and therefore require a separate,
deliberate deployment.

## Run the benchmark

Run it with the Python interpreter whose installed language packages should
be evaluated:

```bash
python3 -m cogs.utils.language_benchmark run \
  --raw-corpus cogs/utils \
  --cleaned-corpus cogs/utils/corpus/audit_cleaned_2026_07_27 \
  --output-dir .codex/language-benchmark
```

List all supported adapters and their availability in the current interpreter:

```bash
python3 -m cogs.utils.language_benchmark list-detectors
```

The default local matrix compares:

- Rai's current single-pass character n-gram Multinomial Naive Bayes;
- Rai's legacy three-stage, two-self-filter implementation;
- raw and audit-cleaned training corpora;
- beginner, advanced, and combined corpus views;
- `(2,2)`, `(3,3)`, `(2,4)`, and `(2,5)` character n-grams;
- cleaned training sets retaining only messages of at least 10 or 16
  characters;
- transfer tests from beginner to advanced messages and vice versa.

Installed pretrained packages are evaluated on the same held-out messages.
Adapters currently exist for langdetect-py, Lingua (English/Spanish,
production ten-language, and optional all-language configurations), langid,
pycld2, gcld3, and cld3. Missing optional packages are reported as skipped;
the benchmark never installs them.

Lingua's all-language mode is opt-in because its local model is much larger:

```bash
python3 -m cogs.utils.language_benchmark run --include-lingua-all
```

Custom n-gram ranges and detector subsets can be supplied:

```bash
python3 -m cogs.utils.language_benchmark run \
  --ngrams 2:2 3:3 2:5 \
  --local-detectors rai_current_nb rai_legacy_nb \
  --package-detectors langdetect lingua_binary lingua_10
```

The Python API is `run_benchmark(BenchmarkConfig(...))`. Empty local or
package detector tuples can be used when evaluating an interpreter that only
contains one category.

## Run a learning curve

The learning-curve mode estimates whether additional unique clean messages
are still improving a trainable detector:

```bash
python3 -m cogs.utils.language_benchmark learning-curve
```

By default it:

- uses the audit-cleaned combined corpus;
- freezes one grouped holdout of 1,500 messages per language;
- excludes every holdout key and every cross-label normalized-text conflict;
- retains one deterministic representative per remaining normalized message;
- balances English and Spanish at the smaller available pool;
- trains nested 10%, 20%, 40%, 60%, 80%, and 100% samples;
- repeats each nested curve five times with fixed detector randomness;
- compares Rai's current single-pass and legacy three-stage Naive Bayes at
  `(2,5)`; and
- reports both all-message and production-oriented `16+` curves.

The 100% point means all balanced, unique, conflict-free representatives. It
is intentionally not the production model's duplicate-retaining all-row
training set. This makes the horizontal axis measure genuinely new
information rather than repeated copies of the same message.

For a longer current-model-only run:

```bash
python3 -m cogs.utils.language_benchmark learning-curve \
  --detectors rai_current_nb \
  --repeats 10 \
  --fractions 0.05 0.1 0.2 0.4 0.6 0.8 1.0
```

Options also allow raw or minimum-length training variants, beginner or
advanced views, alternate n-grams, and a different fixed evaluation size.
The mode writes `results.csv`, `aggregates.csv`, `fits.csv`, `results.json`,
and `report.md` to `.codex/language-learning-curve` by default. Power-law
projections include the estimated accuracy at 10,000 additional unique
messages, 1.5× the observed data, and 2× the observed data. Weak,
boundary-constrained, or sparse-error fits are marked unstable.

The Python API is
`run_learning_curve(LearningCurveConfig(...))` from
`cogs.utils.language_learning_curve`.

## Evaluation design

The evaluation set is sampled deterministically from the cleaned chat corpus.
It contains one representative per normalized text, excludes text groups that
have contradictory English/Spanish labels, and is balanced by language where
enough examples are available. Every occurrence of an evaluation text is
removed from every trainable model's input, including raw-corpus runs. This
prevents exact-message duplicates from leaking across training and evaluation.

Metrics are emitted for all lengths, `<10`, `10-15`, `16-30`, `31+`, and the
production-oriented `16+` subset. Accuracy treats an abstention or an
open-set `other` result as incorrect; coverage and accuracy among covered
predictions are also reported.

The benchmark writes:

- `results.csv` with metrics and local timing/resource measurements;
- `results.json` with the complete configuration, environment, inventory,
  results, and skipped runs;
- `error_examples.jsonl` with a bounded mistake sample for each run;
- `report.md` with comparable `16+` rankings.

The labels still originate from chat-channel membership rather than an
independent linguistic gold standard. Results therefore measure relative
performance on Rai's domain and agreement with the cleaned labels, not
universal language-detection accuracy.
