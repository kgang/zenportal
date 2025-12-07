"""Tests for OpenRouter models service."""

import json
import time
from pathlib import Path

import pytest

from zen_portal.services.openrouter_models import OpenRouterModel, OpenRouterModelsService


class TestOpenRouterModel:
    """Tests for OpenRouterModel dataclass."""

    def test_from_api_dict_basic(self):
        """Test creating model from API response."""
        data = {
            "id": "anthropic/claude-sonnet-4",
            "name": "Claude Sonnet 4",
            "context_length": 200000,
            "pricing": {"prompt": 0.000003, "completion": 0.000015},
            "description": "A great model",
        }
        model = OpenRouterModel.from_api_dict(data)

        assert model.id == "anthropic/claude-sonnet-4"
        assert model.name == "Claude Sonnet 4"
        assert model.context_length == 200000
        assert model.pricing_prompt == 3.0  # per 1M tokens
        assert model.pricing_completion == 15.0
        assert model.description == "A great model"

    def test_from_api_dict_missing_fields(self):
        """Test creating model with minimal data."""
        data = {"id": "test/model"}
        model = OpenRouterModel.from_api_dict(data)

        assert model.id == "test/model"
        assert model.name == "test/model"  # Falls back to ID
        assert model.context_length == 0
        assert model.pricing_prompt == 0.0
        assert model.pricing_completion == 0.0

    def test_short_id(self):
        """Test short_id property."""
        model = OpenRouterModel(
            id="anthropic/claude-sonnet-4",
            name="Claude",
            context_length=0,
            pricing_prompt=0,
            pricing_completion=0,
        )
        assert model.short_id == "claude-sonnet-4"

    def test_short_id_no_provider(self):
        """Test short_id when no provider prefix."""
        model = OpenRouterModel(
            id="gpt-4",
            name="GPT-4",
            context_length=0,
            pricing_prompt=0,
            pricing_completion=0,
        )
        assert model.short_id == "gpt-4"

    def test_provider(self):
        """Test provider property."""
        model = OpenRouterModel(
            id="openai/gpt-4",
            name="GPT-4",
            context_length=0,
            pricing_prompt=0,
            pricing_completion=0,
        )
        assert model.provider == "openai"

    def test_provider_no_prefix(self):
        """Test provider when no prefix."""
        model = OpenRouterModel(
            id="gpt-4",
            name="GPT-4",
            context_length=0,
            pricing_prompt=0,
            pricing_completion=0,
        )
        assert model.provider == ""


class TestOpenRouterModelsService:
    """Tests for OpenRouterModelsService."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """Create temporary cache directory."""
        return tmp_path / "cache"

    @pytest.fixture
    def service(self, temp_cache_dir):
        """Create service with temp cache."""
        return OpenRouterModelsService(cache_dir=temp_cache_dir)

    @pytest.fixture
    def sample_models(self):
        """Sample model list for testing."""
        return [
            OpenRouterModel(
                id="anthropic/claude-sonnet-4",
                name="Claude Sonnet 4",
                context_length=200000,
                pricing_prompt=3.0,
                pricing_completion=15.0,
            ),
            OpenRouterModel(
                id="anthropic/claude-opus-4",
                name="Claude Opus 4",
                context_length=200000,
                pricing_prompt=15.0,
                pricing_completion=75.0,
            ),
            OpenRouterModel(
                id="openai/gpt-4o",
                name="GPT-4o",
                context_length=128000,
                pricing_prompt=2.5,
                pricing_completion=10.0,
            ),
            OpenRouterModel(
                id="google/gemini-pro",
                name="Gemini Pro",
                context_length=32000,
                pricing_prompt=0.5,
                pricing_completion=1.5,
            ),
        ]

    def test_search_models_exact_match(self, service, sample_models):
        """Test exact ID match ranks highest."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("anthropic/claude-sonnet-4")
        assert results[0].id == "anthropic/claude-sonnet-4"

    def test_search_models_prefix_match(self, service, sample_models):
        """Test prefix matching."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("anthropic/claude")
        assert len(results) == 2
        assert all("claude" in r.id for r in results)

    def test_search_models_contains_match(self, service, sample_models):
        """Test substring matching."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("sonnet")
        assert len(results) == 1
        assert results[0].id == "anthropic/claude-sonnet-4"

    def test_search_models_name_match(self, service, sample_models):
        """Test matching by name."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("GPT")
        assert len(results) == 1
        assert results[0].id == "openai/gpt-4o"

    def test_search_models_fuzzy_match(self, service, sample_models):
        """Test fuzzy matching (chars in order)."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("clsnt")  # c-l-s-n-t in claude-sonnet
        assert len(results) >= 1
        assert any("claude-sonnet" in r.id for r in results)

    def test_search_models_empty_query(self, service, sample_models):
        """Test empty query returns all models."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("")
        assert len(results) == len(sample_models)

    def test_search_models_limit(self, service, sample_models):
        """Test limit parameter."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("", limit=2)
        assert len(results) == 2

    def test_search_models_no_match(self, service, sample_models):
        """Test no match returns empty list."""
        service._models = sample_models
        service._last_fetch = time.time()

        results = service.search_models("zzzznonexistent")
        assert len(results) == 0

    def test_cache_save_and_load(self, service, sample_models, temp_cache_dir):
        """Test cache persistence."""
        service._save_cache(sample_models)

        # Create new service instance
        new_service = OpenRouterModelsService(cache_dir=temp_cache_dir)
        loaded = new_service._load_cache()

        assert loaded is not None
        assert len(loaded) == len(sample_models)
        assert loaded[0].id == sample_models[0].id

    def test_cache_ttl_expired(self, service, sample_models, temp_cache_dir):
        """Test expired cache is not loaded."""
        # Save cache with old timestamp
        data = {
            "cached_at": time.time() - (25 * 60 * 60),  # 25 hours ago
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_length": m.context_length,
                    "pricing_prompt": m.pricing_prompt,
                    "pricing_completion": m.pricing_completion,
                    "description": m.description,
                }
                for m in sample_models
            ],
        }
        temp_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = temp_cache_dir / "openrouter_models.json"
        cache_file.write_text(json.dumps(data))

        loaded = service._load_cache()
        assert loaded is None

    def test_cache_ttl_ignored(self, service, sample_models, temp_cache_dir):
        """Test ignore_ttl parameter."""
        # Save cache with old timestamp
        data = {
            "cached_at": time.time() - (25 * 60 * 60),  # 25 hours ago
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_length": m.context_length,
                    "pricing_prompt": m.pricing_prompt,
                    "pricing_completion": m.pricing_completion,
                    "description": m.description,
                }
                for m in sample_models
            ],
        }
        temp_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = temp_cache_dir / "openrouter_models.json"
        cache_file.write_text(json.dumps(data))

        loaded = service._load_cache(ignore_ttl=True)
        assert loaded is not None
        assert len(loaded) == len(sample_models)

    def test_get_model_by_id(self, service, sample_models):
        """Test getting model by ID."""
        service._models = sample_models
        service._last_fetch = time.time()

        model = service.get_model_by_id("openai/gpt-4o")
        assert model is not None
        assert model.name == "GPT-4o"

    def test_get_model_by_id_not_found(self, service, sample_models):
        """Test getting non-existent model."""
        service._models = sample_models
        service._last_fetch = time.time()

        model = service.get_model_by_id("nonexistent/model")
        assert model is None


class TestFuzzyMatch:
    """Tests for fuzzy matching algorithm."""

    @pytest.fixture
    def service(self, tmp_path):
        return OpenRouterModelsService(cache_dir=tmp_path)

    def test_fuzzy_match_positive(self, service):
        """Test positive fuzzy match."""
        assert service._fuzzy_match("abc", "aXbXcX") is True
        assert service._fuzzy_match("clsnt", "claude-sonnet") is True

    def test_fuzzy_match_negative(self, service):
        """Test negative fuzzy match."""
        assert service._fuzzy_match("abc", "acb") is False  # Wrong order
        assert service._fuzzy_match("xyz", "abc") is False

    def test_fuzzy_match_exact(self, service):
        """Test exact string fuzzy matches."""
        assert service._fuzzy_match("test", "test") is True

    def test_fuzzy_match_empty_query(self, service):
        """Test empty query matches anything."""
        assert service._fuzzy_match("", "anything") is True
