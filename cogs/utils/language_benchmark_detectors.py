"""Local-only language detector adapters used by the benchmark harness.

The module deliberately has no Discord imports and imports third-party
detectors only when an adapter is used.  Every adapter presents the same small
interface:

``fit(texts, labels)``
    Train the detector, or do nothing for a pretrained detector.

``initialize()``
    Eagerly load a pretrained package's local model.  Construction itself
    remains lazy so detector discovery never imports optional dependencies.

``predict(texts)``
    Return one normalized label per text: ``"en"``, ``"es"``, or ``"other"``.

``predict_with_confidence(texts)``
    Return ``(label, confidence)`` pairs.  Confidence is ``None`` when a
    package does not expose a useful score.

The adapters never make network requests.  In particular, this module does
not call the bot's OpenAI- or translation-backed language workflows.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import math
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence


NormalizedLabel = str
ConfidenceResult = tuple[NormalizedLabel, float | None]
NgramRange = tuple[int, int]

ENGLISH = "en"
SPANISH = "es"
OTHER = "other"
NORMALIZED_LABELS = frozenset({ENGLISH, SPANISH, OTHER})


class DetectorUnavailableError(RuntimeError):
    """Raised when an optional detector package is not importable."""


class DetectorNotFittedError(RuntimeError):
    """Raised when a trainable detector is used before ``fit``."""


def normalize_language(language: object) -> NormalizedLabel:
    """Normalize a package-specific language value to en/es/other."""

    if language is None:
        return OTHER

    enum_name = getattr(language, "name", None)
    if enum_name:
        language = enum_name

    value = str(language).strip().casefold()
    if not value:
        return OTHER

    # Handles strings such as ``Language.ENGLISH`` and codes such as en-US.
    value = value.rsplit(".", 1)[-1]
    primary_code = value.replace("_", "-").split("-", 1)[0]

    if value in {"english", "eng"} or primary_code == "en":
        return ENGLISH
    if value in {"spanish", "castilian", "spa", "esp", "sp"} or primary_code == "es":
        return SPANISH
    return OTHER


def _text_batch(texts: Iterable[str]) -> list[str]:
    if isinstance(texts, str):
        raise TypeError("texts must be an iterable of strings, not one string")
    values = list(texts)
    if any(not isinstance(text, str) for text in values):
        raise TypeError("every text must be a string")
    return values


def _validate_ngram_range(ngram_range: NgramRange) -> NgramRange:
    if (
        not isinstance(ngram_range, tuple)
        or len(ngram_range) != 2
        or not all(isinstance(value, int) for value in ngram_range)
    ):
        raise TypeError("ngram_range must be a pair of integers")
    minimum, maximum = ngram_range
    if minimum < 1 or maximum < minimum:
        raise ValueError("ngram_range must satisfy 1 <= minimum <= maximum")
    return ngram_range


def _module_available(module_name: str) -> bool:
    if module_name in sys.modules and sys.modules[module_name] is not None:
        return True
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _package_version(distributions: Sequence[str]) -> str | None:
    for distribution in distributions:
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


class DetectorAdapter:
    """Base class for all benchmark detector adapters."""

    name = "base"
    package = "built-in"
    module_name: str | None = None
    distributions: tuple[str, ...] = ()
    pretrained = True
    scope = "unknown"
    confidence_kind = "probability"

    def __init__(self, *, seed: int = 42) -> None:
        self.seed = seed

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "package": self.package,
            "module": self.module_name,
            "version": _package_version(self.distributions),
            "pretrained": self.pretrained,
            "scope": self.scope,
            "supports_batch": True,
            "supports_confidence": True,
            "confidence_kind": self.confidence_kind,
            "requires_network": False,
            "seed": self.seed,
        }

    def fit(
        self,
        texts: Iterable[str],
        labels: Iterable[str],
    ) -> "DetectorAdapter":
        """Initialize a pretrained detector; trainable adapters override this."""

        return self.initialize()

    def initialize(self) -> "DetectorAdapter":
        """Load any local pretrained resources needed by this adapter.

        The base implementation is deliberately a no-op.  Package adapters
        override it, while trainable adapters load their dependencies and
        model state in ``fit``.
        """

        return self

    def predict(self, texts: Iterable[str]) -> list[NormalizedLabel]:
        return [label for label, _ in self.predict_with_confidence(texts)]

    def predict_with_confidence(
        self,
        texts: Iterable[str],
    ) -> list[ConfidenceResult]:
        raise NotImplementedError


_LANGDETECT_LOCK = threading.Lock()


def _set_langdetect_seed(module: Any, factory: Any | None, seed: int) -> None:
    """Set both class- and instance-level seeds across langdetect variants."""

    factory_type = getattr(module, "DetectorFactory", None)
    if factory_type is not None:
        factory_type.seed = seed
    if factory is None:
        return
    set_seed = getattr(factory, "set_seed", None)
    if callable(set_seed):
        set_seed(seed)
    else:
        factory.seed = seed


def _build_langdetect_factory(module: Any, seed: int) -> Any | None:
    """Build and profile-load a DetectorFactory when the package exposes one."""

    factory_type = getattr(module, "DetectorFactory", None)
    if factory_type is None:
        return None

    profile_directory = getattr(module, "PROFILES_DIRECTORY", None)
    if profile_directory is None:
        try:
            factory_module = importlib.import_module(
                f"{module.__name__}.detector_factory"
            )
        except (ImportError, ModuleNotFoundError):
            factory_module = None
        if factory_module is not None:
            profile_directory = getattr(factory_module, "PROFILES_DIRECTORY", None)

    try:
        factory = factory_type()
    except TypeError:
        return None
    load_profile = getattr(factory, "load_profile", None)
    create = getattr(factory, "create", None)
    if not callable(create):
        return None
    if callable(load_profile):
        if profile_directory is None:
            return None
        load_profile(profile_directory)
    _set_langdetect_seed(module, factory, seed)
    return factory


def _langdetect_probability_result(predictions: object) -> ConfidenceResult:
    """Normalize probability objects, pairs, or mappings from package forks."""

    if predictions is None:
        return OTHER, 0.0
    if isinstance(predictions, dict):
        candidates: Iterable[object] = predictions.items()
    else:
        try:
            candidates = list(predictions)  # type: ignore[arg-type]
        except TypeError:
            candidates = [predictions]

    parsed: list[tuple[NormalizedLabel, float]] = []
    for prediction in candidates:
        language = getattr(prediction, "lang", None)
        probability = getattr(prediction, "prob", None)
        if language is None and isinstance(prediction, (tuple, list)):
            if prediction:
                language = prediction[0]
            if len(prediction) > 1:
                probability = prediction[1]
        try:
            confidence = float(probability)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(confidence):
            continue
        parsed.append((normalize_language(language), confidence))

    if not parsed:
        return OTHER, 0.0
    return max(parsed, key=lambda result: result[1])


class _LangdetectAdapter(DetectorAdapter):
    package = "langdetect-py"
    module_name = "langdetect"
    distributions = ("langdetect-py", "langdetect")
    prior_map: dict[str, float] | None = None

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(seed=seed)
        self._module: Any | None = None
        self._factory: Any | None = None
        self._initialized = False

    def initialize(self) -> "_LangdetectAdapter":
        if self._initialized:
            return self

        module = importlib.import_module("langdetect")
        factory = _build_langdetect_factory(module, self.seed)
        if factory is None and self.prior_map is not None:
            raise DetectorUnavailableError(
                "langdetect_binary requires DetectorFactory.create(), "
                "Detector.set_prior_map(), and local language profiles"
            )
        if factory is None and not callable(getattr(module, "detect_langs", None)):
            raise DetectorUnavailableError(
                "langdetect does not expose DetectorFactory or detect_langs"
            )

        _set_langdetect_seed(module, factory, self.seed)
        self._module = module
        self._factory = factory
        self._initialized = True
        return self

    def _probabilities(self, text: str) -> object:
        self.initialize()
        if self._factory is None:
            return self._module.detect_langs(text)

        _set_langdetect_seed(self._module, self._factory, self.seed)
        detector = self._factory.create()
        if self.prior_map is not None:
            set_prior_map = getattr(detector, "set_prior_map", None)
            if not callable(set_prior_map):
                raise DetectorUnavailableError(
                    "langdetect Detector does not expose set_prior_map"
                )
            set_prior_map(dict(self.prior_map))
        detector.append(text)
        return detector.get_probabilities()

    def predict_with_confidence(
        self,
        texts: Iterable[str],
    ) -> list[ConfidenceResult]:
        values = _text_batch(texts)
        self.initialize()
        output: list[ConfidenceResult] = []

        # langdetect seeds Python's process-global random state.  Serializing
        # calls keeps results deterministic even if a benchmark uses threads.
        with _LANGDETECT_LOCK:
            _set_langdetect_seed(self._module, self._factory, self.seed)
            for text in values:
                if not text.strip():
                    output.append((OTHER, 0.0))
                    continue
                try:
                    output.append(
                        _langdetect_probability_result(self._probabilities(text))
                    )
                except Exception:
                    output.append((OTHER, 0.0))
        return output


class LangdetectAdapter(_LangdetectAdapter):
    name = "langdetect"
    scope = "multilingual"


class LangdetectBinaryAdapter(_LangdetectAdapter):
    """langdetect with all prior probability restricted to English/Spanish."""

    name = "langdetect_binary"
    scope = "English and Spanish"
    prior_map = {ENGLISH: 0.5, SPANISH: 0.5}

    @property
    def metadata(self) -> dict[str, object]:
        metadata = super().metadata
        metadata["prior_map"] = dict(self.prior_map)
        return metadata


class _LinguaAdapter(DetectorAdapter):
    package = "lingua-language-detector"
    module_name = "lingua"
    distributions = ("lingua-language-detector",)

    _TEN_LANGUAGE_NAMES = (
        "SPANISH",
        "ENGLISH",
        "FRENCH",
        "ARABIC",
        "PORTUGUESE",
        "JAPANESE",
        "TAGALOG",
        "GERMAN",
        "RUSSIAN",
        "ITALIAN",
    )

    def __init__(self, *, mode: str, seed: int = 42) -> None:
        super().__init__(seed=seed)
        self.mode = mode
        self._language: Any | None = None
        self._detector: Any | None = None

    def _load(self) -> tuple[Any, Any]:
        if self._detector is not None:
            return self._language, self._detector

        module = importlib.import_module("lingua")
        language = module.Language
        builder = module.LanguageDetectorBuilder
        if self.mode == "binary":
            detector_builder = builder.from_languages(
                language.SPANISH,
                language.ENGLISH,
            )
        elif self.mode == "ten":
            detector_builder = builder.from_languages(
                *(getattr(language, name) for name in self._TEN_LANGUAGE_NAMES)
            )
        elif self.mode == "all":
            detector_builder = builder.from_all_languages()
        else:
            raise ValueError(f"Unknown Lingua mode: {self.mode}")

        self._language = language
        self._detector = detector_builder.build()
        return self._language, self._detector

    def initialize(self) -> "_LinguaAdapter":
        self._load()
        return self

    def predict_with_confidence(
        self,
        texts: Iterable[str],
    ) -> list[ConfidenceResult]:
        values = _text_batch(texts)
        _, detector = self._load()
        output: list[ConfidenceResult] = []
        for text in values:
            if not text.strip():
                output.append((OTHER, 0.0))
                continue
            try:
                confidence_values = detector.compute_language_confidence_values(text)
            except Exception:
                output.append((OTHER, 0.0))
                continue
            if not confidence_values:
                output.append((OTHER, 0.0))
                continue
            top = confidence_values[0]
            output.append(
                (
                    normalize_language(getattr(top, "language", None)),
                    float(getattr(top, "value", 0.0)),
                )
            )
        return output

    @property
    def metadata(self) -> dict[str, object]:
        metadata = super().metadata
        metadata["mode"] = self.mode
        return metadata


class LinguaBinaryAdapter(_LinguaAdapter):
    name = "lingua_binary"
    scope = "English and Spanish"

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(mode="binary", seed=seed)


class LinguaTenAdapter(_LinguaAdapter):
    name = "lingua_10"
    scope = "production ten-language set"

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(mode="ten", seed=seed)


class LinguaAllAdapter(_LinguaAdapter):
    name = "lingua_all"
    scope = "all Lingua languages"

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(mode="all", seed=seed)


class LangidAdapter(DetectorAdapter):
    name = "langid"
    package = "langid"
    module_name = "langid"
    distributions = ("langid",)
    scope = "multilingual"

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(seed=seed)
        self._identifier: Any | None = None
        self._normalized_probabilities = False

    def _load(self) -> Any:
        if self._identifier is not None:
            return self._identifier

        module = importlib.import_module("langid")
        try:
            implementation = importlib.import_module("langid.langid")
            self._identifier = implementation.LanguageIdentifier.from_modelstring(
                implementation.model,
                norm_probs=True,
            )
            self._normalized_probabilities = True
        except (AttributeError, ImportError, ModuleNotFoundError):
            self._identifier = module
        return self._identifier

    def initialize(self) -> "LangidAdapter":
        self._load()
        return self

    def predict_with_confidence(
        self,
        texts: Iterable[str],
    ) -> list[ConfidenceResult]:
        values = _text_batch(texts)
        identifier = self._load()
        output: list[ConfidenceResult] = []
        for text in values:
            if not text.strip():
                output.append((OTHER, 0.0))
                continue
            try:
                language, score = identifier.classify(text)
            except Exception:
                output.append((OTHER, 0.0))
                continue
            confidence = float(score) if score is not None else None
            output.append((normalize_language(language), confidence))
        return output

    @property
    def metadata(self) -> dict[str, object]:
        metadata = super().metadata
        metadata["confidence_kind"] = (
            "probability" if self._normalized_probabilities else "package score"
        )
        return metadata


class Pycld2Adapter(DetectorAdapter):
    name = "pycld2"
    package = "pycld2"
    module_name = "pycld2"
    distributions = ("pycld2",)
    scope = "multilingual"

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(seed=seed)
        self._module: Any | None = None

    def _load(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module("pycld2")
        return self._module

    def initialize(self) -> "Pycld2Adapter":
        self._load()
        return self

    def predict_with_confidence(
        self,
        texts: Iterable[str],
    ) -> list[ConfidenceResult]:
        values = _text_batch(texts)
        module = self._load()
        output: list[ConfidenceResult] = []
        for text in values:
            if not text.strip():
                output.append((OTHER, 0.0))
                continue
            try:
                try:
                    _, _, details = module.detect(text, bestEffort=True)
                except TypeError:
                    _, _, details = module.detect(text)
            except Exception:
                output.append((OTHER, 0.0))
                continue
            if not details:
                output.append((OTHER, 0.0))
                continue
            top = details[0]
            language_code = top[1] if len(top) > 1 else None
            percent = float(top[2]) / 100.0 if len(top) > 2 else None
            output.append((normalize_language(language_code), percent))
        return output


def _cld3_result(result: object) -> ConfidenceResult:
    if result is None:
        return OTHER, 0.0
    language = getattr(result, "language", None)
    probability = getattr(result, "probability", None)
    if language is None and isinstance(result, (tuple, list)) and result:
        language = result[0]
        probability = result[1] if len(result) > 1 else None
    confidence = float(probability) if probability is not None else None
    return normalize_language(language), confidence


class _Cld3Adapter(DetectorAdapter):
    scope = "multilingual"

    def __init__(self, *, module_name: str, seed: int = 42) -> None:
        super().__init__(seed=seed)
        self._target_module_name = module_name
        self._module: Any | None = None
        self._identifier: Any | None = None

    def _load(self) -> tuple[Any, Any | None]:
        if self._module is not None:
            return self._module, self._identifier
        self._module = importlib.import_module(self._target_module_name)
        identifier_class = getattr(self._module, "NNetLanguageIdentifier", None)
        if identifier_class is not None:
            try:
                self._identifier = identifier_class(
                    min_num_bytes=0,
                    max_num_bytes=1000,
                )
            except TypeError:
                self._identifier = identifier_class(0, 1000)
        return self._module, self._identifier

    def initialize(self) -> "_Cld3Adapter":
        self._load()
        return self

    def predict_with_confidence(
        self,
        texts: Iterable[str],
    ) -> list[ConfidenceResult]:
        values = _text_batch(texts)
        module, identifier = self._load()
        output: list[ConfidenceResult] = []
        for text in values:
            if not text.strip():
                output.append((OTHER, 0.0))
                continue
            try:
                if identifier is not None:
                    find_language = getattr(
                        identifier,
                        "FindLanguage",
                        getattr(identifier, "find_language", None),
                    )
                    if find_language is None:
                        raise AttributeError("CLD3 identifier has no language method")
                    result = find_language(text)
                else:
                    get_language = getattr(module, "get_language")
                    result = get_language(text)
            except Exception:
                output.append((OTHER, 0.0))
                continue
            output.append(_cld3_result(result))
        return output


class Gcld3Adapter(_Cld3Adapter):
    name = "gcld3"
    package = "gcld3"
    module_name = "gcld3"
    distributions = ("gcld3",)

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(module_name="gcld3", seed=seed)


class Cld3Adapter(_Cld3Adapter):
    name = "cld3"
    package = "cld3"
    module_name = "cld3"
    distributions = ("cld3",)

    def __init__(self, *, seed: int = 42) -> None:
        super().__init__(module_name="cld3", seed=seed)


class _BinaryNaiveBayesAdapter(DetectorAdapter):
    """Shared implementation for local character n-gram NB detectors."""

    package = "scikit-learn"
    module_name = "sklearn"
    distributions = ("scikit-learn",)
    pretrained = False
    scope = "English and Spanish"
    english_threshold = 0.9
    spanish_threshold = 0.1

    def __init__(
        self,
        *,
        ngram_range: NgramRange = (2, 2),
        seed: int = 42,
    ) -> None:
        super().__init__(seed=seed)
        self.ngram_range = _validate_ngram_range(ngram_range)
        self._pipeline: Any | None = None
        self.training_summary: dict[str, object] = {}

    @staticmethod
    def _sklearn_components() -> tuple[Any, Any, Any, Any]:
        feature_module = importlib.import_module("sklearn.feature_extraction.text")
        model_module = importlib.import_module("sklearn.naive_bayes")
        pipeline_module = importlib.import_module("sklearn.pipeline")
        split_module = importlib.import_module("sklearn.model_selection")
        return (
            feature_module.CountVectorizer,
            model_module.MultinomialNB,
            pipeline_module.Pipeline,
            split_module.train_test_split,
        )

    def _new_pipeline(self) -> Any:
        CountVectorizer, MultinomialNB, Pipeline, _ = self._sklearn_components()
        vectorizer = CountVectorizer(
            analyzer="char",
            ngram_range=self.ngram_range,
        )
        return Pipeline(
            [
                ("vectorizer", vectorizer),
                ("model", MultinomialNB()),
            ]
        )

    @staticmethod
    def _training_data(
        texts: Iterable[str],
        labels: Iterable[str],
    ) -> tuple[list[str], list[str]]:
        text_values = _text_batch(texts)
        if isinstance(labels, str):
            raise TypeError("labels must be an iterable, not one string")
        label_values = [normalize_language(label) for label in labels]
        if len(text_values) != len(label_values):
            raise ValueError("texts and labels must have equal lengths")
        if not text_values:
            raise ValueError("training data cannot be empty")
        invalid = set(label_values) - {ENGLISH, SPANISH}
        if invalid:
            raise ValueError("binary NB training labels must be en or es")

        # The production loader concatenates all English messages followed by
        # all Spanish messages.  Preserve that order for deterministic parity.
        english = [
            text for text, label in zip(text_values, label_values) if label == ENGLISH
        ]
        spanish = [
            text for text, label in zip(text_values, label_values) if label == SPANISH
        ]
        if not english or not spanish:
            raise ValueError("training data must contain both English and Spanish")
        ordered_texts = english + spanish
        internal_labels = [ENGLISH] * len(english) + ["sp"] * len(spanish)
        return ordered_texts, internal_labels

    def _require_pipeline(self) -> Any:
        if self._pipeline is None:
            raise DetectorNotFittedError(f"{self.name} must be fitted before prediction")
        return self._pipeline

    def predict_probabilities(
        self,
        texts: Iterable[str],
    ) -> list[tuple[float, float]]:
        values = _text_batch(texts)
        if not values:
            return []
        pipeline = self._require_pipeline()
        probabilities = pipeline.predict_proba(values)
        classes = list(pipeline.classes_)
        try:
            english_index = classes.index(ENGLISH)
            spanish_index = classes.index("sp")
        except ValueError as exc:
            raise RuntimeError(
                f"{self.name} was fitted without both expected classes"
            ) from exc
        return [
            (float(row[english_index]), float(row[spanish_index]))
            for row in probabilities
        ]

    # Familiar spelling for callers that expect a sklearn-like method.
    predict_proba = predict_probabilities

    def serialized_size_bytes(self) -> int:
        """Return the in-memory pickle size of the fitted sklearn pipeline."""

        import pickle

        pipeline = self._require_pipeline()
        return len(pickle.dumps(pipeline, protocol=pickle.HIGHEST_PROTOCOL))

    def predict_with_confidence(
        self,
        texts: Iterable[str],
    ) -> list[ConfidenceResult]:
        output: list[ConfidenceResult] = []
        for english_probability, spanish_probability in self.predict_probabilities(texts):
            if english_probability > self.english_threshold:
                output.append((ENGLISH, english_probability))
            elif english_probability < self.spanish_threshold:
                output.append((SPANISH, spanish_probability))
            else:
                output.append((OTHER, max(english_probability, spanish_probability)))
        return output

    @property
    def metadata(self) -> dict[str, object]:
        metadata = super().metadata
        metadata.update(
            {
                "ngram_range": self.ngram_range,
                "english_threshold": self.english_threshold,
                "spanish_threshold": self.spanish_threshold,
                "training_summary": dict(self.training_summary),
            }
        )
        return metadata


class SklearnNaiveBayesAdapter(_BinaryNaiveBayesAdapter):
    """Single-pass CountVectorizer(char) + MultinomialNB baseline."""

    name = "sklearn_nb"

    def fit(
        self,
        texts: Iterable[str],
        labels: Iterable[str],
    ) -> "SklearnNaiveBayesAdapter":
        ordered_texts, internal_labels = self._training_data(texts, labels)
        self._pipeline = self._new_pipeline()
        self._pipeline.fit(ordered_texts, internal_labels)
        self.training_summary = {
            "stages": 1,
            "input_rows": len(ordered_texts),
            "fit_rows": len(ordered_texts),
            "self_filter_rounds": 0,
        }
        return self


class RaiCurrentNaiveBayesAdapter(_BinaryNaiveBayesAdapter):
    """Exact structure of Rai's current three-stage/two-filter model."""

    name = "rai_current_nb"
    test_size = 0.05

    def _fit_stage(
        self,
        texts: list[str],
        labels: list[str],
    ) -> tuple[Any, int]:
        if set(labels) != {ENGLISH, "sp"}:
            raise ValueError("each production-parity stage needs both languages")
        _, _, _, train_test_split = self._sklearn_components()
        train_texts, _, train_labels, _ = train_test_split(
            texts,
            labels,
            test_size=self.test_size,
            random_state=self.seed,
        )
        if set(train_labels) != {ENGLISH, "sp"}:
            raise ValueError(
                "the production-style split omitted a language; use more training rows"
            )
        pipeline = self._new_pipeline()
        pipeline.fit(train_texts, train_labels)
        return pipeline, len(train_texts)

    @staticmethod
    def _filter_expected_predictions(
        pipeline: Any,
        texts: list[str],
        labels: list[str],
    ) -> tuple[list[str], list[str]]:
        predictions = pipeline.predict(texts)
        kept = [
            (text, label)
            for text, label, prediction in zip(texts, labels, predictions)
            if prediction == label
        ]
        return [text for text, _ in kept], [label for _, label in kept]

    def fit(
        self,
        texts: Iterable[str],
        labels: Iterable[str],
    ) -> "RaiCurrentNaiveBayesAdapter":
        original_texts, original_labels = self._training_data(texts, labels)

        first, first_fit_rows = self._fit_stage(original_texts, original_labels)
        first_filtered_texts, first_filtered_labels = (
            self._filter_expected_predictions(
                first,
                original_texts,
                original_labels,
            )
        )

        second, second_fit_rows = self._fit_stage(
            first_filtered_texts,
            first_filtered_labels,
        )
        # This deliberately filters the original corpus again, matching the
        # nested make_set(...) calls in helper_functions.py.
        second_filtered_texts, second_filtered_labels = (
            self._filter_expected_predictions(
                second,
                original_texts,
                original_labels,
            )
        )

        self._pipeline, final_fit_rows = self._fit_stage(
            second_filtered_texts,
            second_filtered_labels,
        )
        self.training_summary = {
            "stages": 3,
            "input_rows": len(original_texts),
            "stage_input_rows": [
                len(original_texts),
                len(first_filtered_texts),
                len(second_filtered_texts),
            ],
            "stage_fit_rows": [
                first_fit_rows,
                second_fit_rows,
                final_fit_rows,
            ],
            "first_filter_removed": len(original_texts) - len(first_filtered_texts),
            "second_filter_removed": len(original_texts) - len(second_filtered_texts),
            "self_filter_rounds": 2,
            "test_size_each_stage": self.test_size,
        }
        return self


@dataclass(frozen=True)
class DetectorSpec:
    name: str
    module_name: str
    package: str
    distributions: tuple[str, ...]
    pretrained: bool
    scope: str
    description: str
    factory: Callable[[NgramRange, int], DetectorAdapter]

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "module": self.module_name,
            "package": self.package,
            "version": _package_version(self.distributions),
            "available": _module_available(self.module_name),
            "pretrained": self.pretrained,
            "scope": self.scope,
            "description": self.description,
            "requires_network": False,
        }


def _pretrained_factory(
    adapter_type: type[DetectorAdapter],
) -> Callable[[NgramRange, int], DetectorAdapter]:
    def factory(_: NgramRange, seed: int) -> DetectorAdapter:
        return adapter_type(seed=seed)

    return factory


_DETECTOR_SPECS: dict[str, DetectorSpec] = {
    "sklearn_nb": DetectorSpec(
        name="sklearn_nb",
        module_name="sklearn",
        package="scikit-learn",
        distributions=("scikit-learn",),
        pretrained=False,
        scope="English and Spanish",
        description="Single-pass character n-gram MultinomialNB baseline.",
        factory=lambda ngram_range, seed: SklearnNaiveBayesAdapter(
            ngram_range=ngram_range,
            seed=seed,
        ),
    ),
    "rai_current_nb": DetectorSpec(
        name="rai_current_nb",
        module_name="sklearn",
        package="scikit-learn",
        distributions=("scikit-learn",),
        pretrained=False,
        scope="English and Spanish",
        description="Rai production-parity three-stage, two-filter character NB.",
        factory=lambda ngram_range, seed: RaiCurrentNaiveBayesAdapter(
            ngram_range=ngram_range,
            seed=seed,
        ),
    ),
    "langdetect": DetectorSpec(
        name="langdetect",
        module_name="langdetect",
        package="langdetect-py",
        distributions=("langdetect-py", "langdetect"),
        pretrained=True,
        scope="multilingual",
        description="Seeded langdetect-py detector.",
        factory=_pretrained_factory(LangdetectAdapter),
    ),
    "langdetect_binary": DetectorSpec(
        name="langdetect_binary",
        module_name="langdetect",
        package="langdetect-py",
        distributions=("langdetect-py", "langdetect"),
        pretrained=True,
        scope="English and Spanish",
        description=(
            "Seeded langdetect-py with equal English/Spanish prior probability."
        ),
        factory=_pretrained_factory(LangdetectBinaryAdapter),
    ),
    "lingua_binary": DetectorSpec(
        name="lingua_binary",
        module_name="lingua",
        package="lingua-language-detector",
        distributions=("lingua-language-detector",),
        pretrained=True,
        scope="English and Spanish",
        description="Lingua restricted to English and Spanish.",
        factory=_pretrained_factory(LinguaBinaryAdapter),
    ),
    "lingua_10": DetectorSpec(
        name="lingua_10",
        module_name="lingua",
        package="lingua-language-detector",
        distributions=("lingua-language-detector",),
        pretrained=True,
        scope="production ten-language set",
        description="Lingua configured with the bot's ten-language set.",
        factory=_pretrained_factory(LinguaTenAdapter),
    ),
    "lingua_all": DetectorSpec(
        name="lingua_all",
        module_name="lingua",
        package="lingua-language-detector",
        distributions=("lingua-language-detector",),
        pretrained=True,
        scope="all Lingua languages",
        description="Lingua configured with every supported language.",
        factory=_pretrained_factory(LinguaAllAdapter),
    ),
    "langid": DetectorSpec(
        name="langid",
        module_name="langid",
        package="langid",
        distributions=("langid",),
        pretrained=True,
        scope="multilingual",
        description="langid.py with normalized probabilities when supported.",
        factory=_pretrained_factory(LangidAdapter),
    ),
    "pycld2": DetectorSpec(
        name="pycld2",
        module_name="pycld2",
        package="pycld2",
        distributions=("pycld2",),
        pretrained=True,
        scope="multilingual",
        description="Compact Language Detector 2 Python bindings.",
        factory=_pretrained_factory(Pycld2Adapter),
    ),
    "gcld3": DetectorSpec(
        name="gcld3",
        module_name="gcld3",
        package="gcld3",
        distributions=("gcld3",),
        pretrained=True,
        scope="multilingual",
        description="Google Compact Language Detector 3 bindings.",
        factory=_pretrained_factory(Gcld3Adapter),
    ),
    "cld3": DetectorSpec(
        name="cld3",
        module_name="cld3",
        package="cld3",
        distributions=("cld3",),
        pretrained=True,
        scope="multilingual",
        description="Alternative CLD3 Python bindings.",
        factory=_pretrained_factory(Cld3Adapter),
    ),
}


def detector_specs() -> list[dict[str, object]]:
    """Return discovery metadata for every supported adapter."""

    return [spec.metadata() for spec in _DETECTOR_SPECS.values()]


def available_detector_specs() -> list[dict[str, object]]:
    """Return discovery metadata for adapters importable in this interpreter."""

    return [spec for spec in detector_specs() if spec["available"]]


def create_detector(
    name: str,
    ngram_range: NgramRange = (2, 2),
    seed: int = 42,
) -> DetectorAdapter:
    """Create a detector by stable registry name.

    Optional dependencies are still imported lazily on first ``fit`` or
    ``predict``; this function only verifies that their module is discoverable.
    """

    normalized_name = name.strip().casefold().replace("-", "_")
    try:
        spec = _DETECTOR_SPECS[normalized_name]
    except KeyError as exc:
        available_names = ", ".join(_DETECTOR_SPECS)
        raise KeyError(
            f"Unknown detector {name!r}. Known detectors: {available_names}"
        ) from exc

    validated_ngram_range = _validate_ngram_range(ngram_range)
    if not _module_available(spec.module_name):
        raise DetectorUnavailableError(
            f"{spec.name} requires the optional {spec.package!r} package "
            f"(import module {spec.module_name!r})"
        )
    return spec.factory(validated_ngram_range, seed)


__all__ = [
    "Cld3Adapter",
    "ConfidenceResult",
    "DetectorAdapter",
    "DetectorNotFittedError",
    "DetectorSpec",
    "DetectorUnavailableError",
    "ENGLISH",
    "Gcld3Adapter",
    "LangdetectAdapter",
    "LangdetectBinaryAdapter",
    "LangidAdapter",
    "LinguaAllAdapter",
    "LinguaBinaryAdapter",
    "LinguaTenAdapter",
    "NORMALIZED_LABELS",
    "OTHER",
    "Pycld2Adapter",
    "RaiCurrentNaiveBayesAdapter",
    "SPANISH",
    "SklearnNaiveBayesAdapter",
    "available_detector_specs",
    "create_detector",
    "detector_specs",
    "normalize_language",
]
