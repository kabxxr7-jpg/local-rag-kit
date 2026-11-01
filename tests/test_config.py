from __future__ import annotations

import pytest

from local_rag.config import Config, load_config, validate
from local_rag.errors import ConfigError


def test_defaults_are_the_documented_ones():
    c = Config()
    assert (c.embed_model, c.llm_model) == ("nomic-embed-text", "llama3.2:1b")
    assert (c.chunk_size, c.chunk_overlap, c.k) == (500, 80, 4)
    assert c.min_score == 0.60
    assert c.num_ctx == 4096 and c.num_predict == 256
    assert c.on_overflow == "trim" and c.extract_mode == "layout"
    assert c.ollama_host == "http://127.0.0.1:11434"


def test_defaults_contain_no_personal_path():
    assert "/Users/" not in repr(Config()) and not Config().store_dir.startswith("/")


def test_environment_overrides_defaults_and_is_typed():
    c = load_config(env={"LOCAL_RAG_K": "7", "LOCAL_RAG_MIN_SCORE": "0.45", "LOCAL_RAG_LLM_MODEL": "other:3b"})
    assert c.k == 7 and isinstance(c.k, int)
    assert c.min_score == 0.45
    assert c.llm_model == "other:3b"


def test_empty_prefix_can_be_set_from_the_environment():
    c = load_config(env={"LOCAL_RAG_EMBED_DOC_PREFIX": "", "LOCAL_RAG_EMBED_QUERY_PREFIX": ""})
    assert c.embed_doc_prefix == "" and c.embed_query_prefix == ""


def test_file_is_below_environment_and_flags_are_above(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('k = 2\nchunk_size = 300\nllm_model = "from-file"\n')
    c = load_config(env={"LOCAL_RAG_K": "9"}, file=str(f))
    assert c.k == 9 and c.chunk_size == 300 and c.llm_model == "from-file"
    c = load_config(env={"LOCAL_RAG_K": "9"}, file=str(f), overrides={"k": 3})
    assert c.k == 3


def test_file_named_by_environment(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text("k = 6\n")
    assert load_config(env={"LOCAL_RAG_CONFIG": str(f)}).k == 6


def test_none_override_is_ignored():
    assert load_config(env={}, overrides={"k": None, "store_dir": None}).k == 4


def test_unknown_key_in_file_lists_the_known_ones(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text("chunksize = 300\n")
    with pytest.raises(ConfigError, match=r"unknown setting\(s\): chunksize.*Known:"):
        load_config(env={}, file=str(f))


def test_missing_and_broken_file(tmp_path):
    with pytest.raises(ConfigError, match="does not exist"):
        load_config(env={}, file=str(tmp_path / "nope.toml"))
    bad = tmp_path / "bad.toml"
    bad.write_text("k = = 1")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(env={}, file=str(bad))


def test_wrong_type_names_the_setting_and_where_it_came_from():
    with pytest.raises(ConfigError, match=r"'k' \(from environment variable LOCAL_RAG_K\)"):
        load_config(env={"LOCAL_RAG_K": "many"})


def test_unknown_override_is_an_error():
    with pytest.raises(ConfigError, match="Unknown setting"):
        load_config(env={}, overrides={"kk": 1})


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"chunk_overlap": 500}, "chunk_overlap"),
        ({"chunk_overlap": -1}, "chunk_overlap"),
        ({"chunk_size": 20, "chunk_overlap": 0}, "chunk_size"),
        ({"k": 0}, "k is 0"),
        ({"min_score": 1.5}, "min_score"),
        ({"min_score": -1.5}, "min_score"),
        ({"num_ctx": 100}, "num_ctx"),
        ({"num_predict": 4096}, "num_predict"),
        ({"num_predict": 0}, "num_predict"),
        ({"chars_per_token": 0}, "chars_per_token"),
        ({"on_overflow": "ignore"}, "on_overflow"),
        ({"extract_mode": "ocr"}, "extract_mode"),
        ({"embedder": "magic"}, "embedder"),
        ({"fake_dim": 2}, "fake_dim"),
    ],
)
def test_validation_rejects_contradictions(changes, message):
    with pytest.raises(ConfigError, match=message):
        validate(Config(**changes))


def test_boundaries_that_are_allowed():
    validate(Config(chunk_size=50, chunk_overlap=0, min_score=-1.0, k=1))
    validate(Config(min_score=1.0, chunk_size=100, chunk_overlap=99))


def test_yes_no_is_not_a_number():
    with pytest.raises(ConfigError):
        load_config(env={}, overrides={"k": True})
