from __future__ import annotations

import importlib.util
import sys
import types
from types import SimpleNamespace

import pytest

from cogs.utils import language_benchmark_detectors as detectors


def test_language_normalization():
    assert detectors.normalize_language("en-US") == "en"
    assert detectors.normalize_language("English") == "en"
    assert detectors.normalize_language("spa") == "es"
    assert detectors.normalize_language("Language.SPANISH") == "es"
    assert detectors.normalize_language("fr") == "other"
    assert detectors.normalize_language(None) == "other"


def test_discovery_exposes_all_stable_names():
    specs = {spec["name"]: spec for spec in detectors.detector_specs()}
    assert {
        "sklearn_nb",
        "rai_current_nb",
        "rai_legacy_nb",
        "langdetect",
        "langdetect_binary",
        "lingua_binary",
        "lingua_10",
        "lingua_all",
        "langid",
        "pycld2",
        "gcld3",
        "cld3",
    } <= specs.keys()
    assert all(spec["requires_network"] is False for spec in specs.values())
    assert all(spec["available"] for spec in detectors.available_detector_specs())


def test_create_detector_rejects_unknown_name():
    with pytest.raises(KeyError, match="Unknown detector"):
        detectors.create_detector("not-a-detector")


def test_create_detector_reports_missing_optional_dependency(monkeypatch):
    monkeypatch.setattr(detectors, "_module_available", lambda _: False)
    with pytest.raises(detectors.DetectorUnavailableError, match="langdetect-py"):
        detectors.create_detector("langdetect")


@pytest.mark.parametrize(
    "ngram_range, exception",
    [
        ((0, 2), ValueError),
        ((3, 2), ValueError),
        ([2, 2], TypeError),
    ],
)
def test_ngram_validation(ngram_range, exception):
    with pytest.raises(exception):
        detectors.SklearnNaiveBayesAdapter(ngram_range=ngram_range)


def test_batch_argument_does_not_accept_one_string():
    adapter = detectors.LangdetectAdapter()
    with pytest.raises(TypeError, match="iterable of strings"):
        adapter.predict("this is one string")


def test_base_initialize_is_an_explicit_noop():
    adapter = detectors.DetectorAdapter()
    assert adapter.initialize() is adapter


def test_langdetect_adapter_is_seeded_and_normalizes(monkeypatch):
    fake_module = types.ModuleType("langdetect")

    class DetectorFactory:
        seed = None

    def detect_langs(text):
        if text == "hello":
            return [SimpleNamespace(lang="en", prob=0.98)]
        if text == "hola":
            return [SimpleNamespace(lang="es", prob=0.97)]
        if text == "bonjour":
            return [SimpleNamespace(lang="fr", prob=0.96)]
        raise ValueError("undetectable")

    fake_module.DetectorFactory = DetectorFactory
    fake_module.detect_langs = detect_langs
    monkeypatch.setitem(sys.modules, "langdetect", fake_module)

    adapter = detectors.create_detector("langdetect", seed=17)
    assert adapter.fit([], []) is adapter
    assert adapter.predict(["hello", "hola", "bonjour", "", "?"]) == [
        "en",
        "es",
        "other",
        "other",
        "other",
    ]
    assert DetectorFactory.seed == 17
    assert adapter.metadata["requires_network"] is False


def test_langdetect_binary_uses_factory_per_text_and_equal_priors(monkeypatch):
    fake_module = types.ModuleType("langdetect")
    fake_module.PROFILES_DIRECTORY = "/bundled/langdetect/profiles"

    class FakeDetector:
        def __init__(self, factory):
            self.factory = factory
            self.text = None
            self.prior = None

        def set_prior_map(self, prior):
            self.prior = prior
            self.factory.priors.append(prior)

        def append(self, text):
            self.text = text

        def get_probabilities(self):
            if self.text == "hello":
                # Exercise probability-object handling.
                return [
                    SimpleNamespace(lang="en", prob=0.93),
                    SimpleNamespace(lang="es", prob=0.07),
                ]
            # Exercise mapping handling and do not rely on package sort order.
            return {"en": 0.08, "es": 0.92}

    class DetectorFactory:
        seed = None
        instances = []

        def __init__(self):
            self.loaded_profile = None
            self.instance_seed = None
            self.create_count = 0
            self.priors = []
            self.__class__.instances.append(self)

        def load_profile(self, directory):
            self.loaded_profile = directory

        def set_seed(self, seed):
            self.instance_seed = seed

        def create(self):
            self.create_count += 1
            return FakeDetector(self)

    fake_module.DetectorFactory = DetectorFactory
    monkeypatch.setitem(sys.modules, "langdetect", fake_module)

    adapter = detectors.create_detector("langdetect_binary", seed=23)
    assert DetectorFactory.instances == []
    assert adapter.initialize() is adapter
    assert adapter.initialize() is adapter

    factory = DetectorFactory.instances[0]
    assert len(DetectorFactory.instances) == 1
    assert factory.loaded_profile == fake_module.PROFILES_DIRECTORY
    assert factory.instance_seed == 23
    assert DetectorFactory.seed == 23
    assert adapter.predict_with_confidence(["hello", "hola", ""]) == [
        ("en", 0.93),
        ("es", 0.92),
        ("other", 0.0),
    ]
    assert factory.create_count == 2
    assert factory.priors == [{"en": 0.5, "es": 0.5}] * 2
    assert adapter.metadata["prior_map"] == {"en": 0.5, "es": 0.5}


def _fake_lingua_module():
    fake_module = types.ModuleType("lingua")

    class Language:
        SPANISH = "SPANISH"
        ENGLISH = "ENGLISH"
        FRENCH = "FRENCH"
        ARABIC = "ARABIC"
        PORTUGUESE = "PORTUGUESE"
        JAPANESE = "JAPANESE"
        TAGALOG = "TAGALOG"
        GERMAN = "GERMAN"
        RUSSIAN = "RUSSIAN"
        ITALIAN = "ITALIAN"

    class FakeDetector:
        def compute_language_confidence_values(self, text):
            if text == "hello":
                return [SimpleNamespace(language=Language.ENGLISH, value=0.99)]
            if text == "hola":
                return [SimpleNamespace(language=Language.SPANISH, value=0.98)]
            return [SimpleNamespace(language=Language.FRENCH, value=0.95)]

    class FakeBuilder:
        calls = []

        @classmethod
        def from_languages(cls, *languages):
            cls.calls.append(("languages", languages))
            return cls()

        @classmethod
        def from_all_languages(cls):
            cls.calls.append(("all", ()))
            return cls()

        def build(self):
            return FakeDetector()

    fake_module.Language = Language
    fake_module.LanguageDetectorBuilder = FakeBuilder
    return fake_module, FakeBuilder


def test_lingua_modes_build_lazily_and_normalize(monkeypatch):
    fake_module, builder = _fake_lingua_module()
    monkeypatch.setitem(sys.modules, "lingua", fake_module)

    binary = detectors.create_detector("lingua_binary")
    ten = detectors.create_detector("lingua_10")
    all_languages = detectors.create_detector("lingua_all")
    assert builder.calls == []

    assert binary.initialize() is binary
    assert builder.calls[0][0] == "languages"
    assert len(builder.calls[0][1]) == 2
    assert binary.predict(["hello", "hola", "bonjour"]) == ["en", "es", "other"]
    assert ten.predict(["hello"]) == ["en"]
    assert all_languages.predict(["bonjour"]) == ["other"]

    assert builder.calls[1][0] == "languages"
    assert len(builder.calls[1][1]) == 10
    assert builder.calls[2][0] == "all"


def test_lingua_ten_languages_exactly_match_message_cog():
    assert detectors.LinguaTenAdapter._TEN_LANGUAGE_NAMES == (
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


def test_pycld2_adapter_normalizes_percent_confidence(monkeypatch):
    fake_module = types.ModuleType("pycld2")

    def detect(text, bestEffort=False):
        code = "es" if text == "hola" else "de"
        return True, len(text), [(code, code, 87, 100)]

    fake_module.detect = detect
    monkeypatch.setitem(sys.modules, "pycld2", fake_module)

    adapter = detectors.create_detector("pycld2")
    assert adapter.initialize() is adapter
    assert adapter._module is fake_module
    assert adapter.predict_with_confidence(["hola", "hallo"]) == [
        ("es", 0.87),
        ("other", 0.87),
    ]


@pytest.mark.parametrize("adapter_name", ["gcld3", "cld3"])
def test_cld3_adapters_normalize_results(monkeypatch, adapter_name):
    fake_module = types.ModuleType(adapter_name)

    class Identifier:
        def __init__(self, min_num_bytes=0, max_num_bytes=1000):
            pass

        def FindLanguage(self, text):
            return SimpleNamespace(
                language="en" if text == "hello" else "pt",
                probability=0.91,
                is_reliable=True,
            )

    fake_module.NNetLanguageIdentifier = Identifier
    monkeypatch.setitem(sys.modules, adapter_name, fake_module)
    adapter = detectors.create_detector(adapter_name)
    assert adapter.predict(["hello", "olá"]) == ["en", "other"]


SKLEARN_AVAILABLE = importlib.util.find_spec("sklearn") is not None


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn is optional")
def test_single_pass_sklearn_nb_interface():
    texts, labels = _clear_binary_training_data()
    adapter = detectors.create_detector("sklearn_nb", ngram_range=(2, 4))

    assert adapter.fit(texts, labels) is adapter
    probabilities = adapter.predict_probabilities(
        ["hello this is clearly english", "hola esta frase es claramente española"]
    )
    assert len(probabilities) == 2
    assert all(abs(english + spanish - 1.0) < 1e-9 for english, spanish in probabilities)
    assert adapter.predict(
        ["hello this is clearly english", "hola esta frase es claramente española"]
    ) == ["en", "es"]
    assert adapter.metadata["ngram_range"] == (2, 4)
    assert adapter.metadata["training_summary"]["stages"] == 1
    assert adapter.serialized_size_bytes() > 0


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn is optional")
def test_sklearn_serialized_size_requires_a_fitted_pipeline():
    adapter = detectors.create_detector("sklearn_nb")
    with pytest.raises(detectors.DetectorNotFittedError):
        adapter.serialized_size_bytes()


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn is optional")
def test_rai_current_nb_runs_one_production_stage():
    texts, labels = _clear_binary_training_data()
    adapter = detectors.create_detector("rai_current_nb", ngram_range=(2, 5), seed=42)
    adapter.fit(texts, labels)

    summary = adapter.metadata["training_summary"]
    assert summary["stages"] == 1
    assert summary["self_filter_rounds"] == 0
    assert summary["fit_rows"] == len(texts)
    assert adapter.metadata["ngram_range"] == (2, 5)
    assert adapter.predict(
        ["hello this is clearly english", "hola esta frase es claramente española"]
    ) == ["en", "es"]


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn is optional")
def test_rai_legacy_nb_runs_three_production_style_stages():
    texts, labels = _clear_binary_training_data()
    adapter = detectors.create_detector("rai_legacy_nb", ngram_range=(2, 2), seed=42)
    adapter.fit(texts, labels)

    summary = adapter.metadata["training_summary"]
    assert summary["stages"] == 3
    assert summary["self_filter_rounds"] == 2
    assert len(summary["stage_input_rows"]) == 3
    assert len(summary["stage_fit_rows"]) == 3
    assert adapter.predict(
        ["hello this is clearly english", "hola esta frase es claramente española"]
    ) == ["en", "es"]


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn is optional")
def test_nb_abstention_uses_production_thresholds():
    texts, labels = _clear_binary_training_data()
    adapter = detectors.create_detector("sklearn_nb")
    adapter.fit(texts, labels)

    class FakePipeline:
        classes_ = ["en", "sp"]

        @staticmethod
        def predict_proba(values):
            return [[0.95, 0.05], [0.05, 0.95], [0.50, 0.50]]

    adapter._pipeline = FakePipeline()
    assert adapter.predict(["a", "b", "c"]) == ["en", "es", "other"]


def _clear_binary_training_data():
    english = [
        f"hello this is a clearly written english chat message number {index}"
        for index in range(80)
    ]
    spanish = [
        f"hola esta es una frase claramente escrita en español numero {index}"
        for index in range(80)
    ]
    return english + spanish, ["en"] * len(english) + ["es"] * len(spanish)
