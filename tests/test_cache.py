"""Тесты дискового кэша ответов LLM."""

from __future__ import annotations

from vanya import cache


def test_put_get_roundtrip(tmp_path):
    key = cache.make_key("model", "risks", "текст")
    payload = {"ok": True, "summary": "ок", "risks": []}
    cache.put(tmp_path, key, payload)
    assert cache.get(tmp_path, key) == payload


def test_missing_key_returns_none(tmp_path):
    assert cache.get(tmp_path, "нет-такого-ключа") is None


def test_cache_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VANYA_CACHE", "0")
    key = cache.make_key("x")
    cache.put(tmp_path, key, {"ok": True})
    assert cache.get(tmp_path, key) is None


def test_corrupted_file_returns_none(tmp_path):
    key = cache.make_key("x")
    folder = cache.cache_dir(tmp_path)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text("{битый json", encoding="utf-8")
    assert cache.get(tmp_path, key) is None
