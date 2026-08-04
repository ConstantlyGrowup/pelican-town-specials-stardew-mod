"""Explicit local capability probe for the configured OpenAI-compatible provider.

Reads PTS_OPENAI_BASE_URL, PTS_OPENAI_API_KEY, PTS_VISION_MODEL, PTS_TEXT_MODEL
and PTS_IMAGE_MODEL. Writes a redacted capability report to the ignored
output/spikes/provider-capabilities.json. Never writes the Key, image bytes,
full prompts, or full provider responses. Without a Key the script does not
touch the network and reports every capability as unsupported.
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from pelican_town_specials.application.settings import ProviderSettings
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.secret_store import ApiKeySource, SecretValue
from pelican_town_specials.providers import OpenAICompatibleGateway
from pelican_town_specials.providers.contracts import (
    AskGusDesignRequest,
    CapabilityResult,
    DishAnalysisRequest,
    ImageGenerationRequest,
    ImageMediaType,
    ImageOperation,
    ProviderCapabilities,
    ProviderImageInput,
)
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_PATH = _REPO_ROOT / "output" / "spikes" / "provider-capabilities.json"


class _EnvSecretStore:
    def __init__(self, key: str | None) -> None:
        self._key = key

    def get_api_key(self) -> SecretValue | None:
        return SecretValue(self._key) if self._key else None

    def get_source(self) -> ApiKeySource:
        return ApiKeySource.NONE


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _tiny_png() -> ProviderImageInput:
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "red").save(output, format="PNG")
    return ProviderImageInput(data=output.getvalue(), media_type=ImageMediaType.PNG)


def _settings() -> ProviderSettings:
    return ProviderSettings(
        base_url=_env("PTS_OPENAI_BASE_URL") or "https://yibuapi.com/v1",
        vision_model=_env("PTS_VISION_MODEL"),
        text_model=_env("PTS_TEXT_MODEL"),
        image_model=_env("PTS_IMAGE_MODEL"),
    )


def _failed(reason: str) -> CapabilityResult:
    return CapabilityResult(supported=False, elapsedMs=0, note=reason)


def _run_probe() -> ProviderCapabilities:
    api_key = _env("PTS_OPENAI_API_KEY")
    if not api_key:
        return ProviderCapabilities(
            chatMultimodal=_failed("not configured"),
            chatJsonSchema=_failed("not configured"),
            chatJsonOnly=_failed("not configured"),
            imageEdits=_failed("not configured"),
            imageGenerations=_failed("not configured"),
        )

    settings = _settings()
    gateway = OpenAICompatibleGateway(
        settings=settings,
        secret_store=_EnvSecretStore(api_key),
    )
    image = _tiny_png()

    async def probe_all() -> ProviderCapabilities:
        chat_multimodal = _failed("not attempted")
        chat_json_schema = _failed("not attempted")
        chat_json_only = _failed("not attempted")
        image_edits = _failed("not attempted")
        image_generations = _failed("not attempted")

        analysis: Any = None
        start = asyncio.get_event_loop().time()
        try:
            analysis = await gateway.analyze_dish(
                DishAnalysisRequest(
                    image=image, context_text=None, language=Language.ZH_CN,
                    request_id=uuid4(),
                )
            )
            chat_multimodal = CapabilityResult(
                supported=True,
                elapsedMs=int((asyncio.get_event_loop().time() - start) * 1000),
                note="structured dish analysis succeeded",
            )
        except AppError as exc:
            chat_multimodal = _failed(exc.code)
        except Exception as exc:  # noqa: BLE001
            chat_multimodal = _failed(type(exc).__name__)
        # analyze_dish tries strict json_schema first; its outcome is the
        # best evidence for JSON Schema support on this provider.
        chat_json_schema = chat_multimodal

        start = asyncio.get_event_loop().time()
        try:
            await gateway.design_ask_gus(
                AskGusDesignRequest(
                    analysis=analysis or _placeholder_analysis(),
                    context_text=None,
                    language=Language.ZH_CN,
                    request_id=uuid4(),
                ),
                json_only=True,
            )
            chat_json_only = CapabilityResult(supported=True, elapsedMs=int((asyncio.get_event_loop().time() - start) * 1000), note="json-only design succeeded")
        except AppError as exc:
            chat_json_only = _failed(exc.code)
        except Exception as exc:  # noqa: BLE001
            chat_json_only = _failed(type(exc).__name__)

        start = asyncio.get_event_loop().time()
        try:
            await gateway.generate_image(
                ImageGenerationRequest(
                    operation=ImageOperation.EDIT,
                    prompt="a tiny red square",
                    source_images=[image],
                    size="256x256",
                    request_id=uuid4(),
                )
            )
            image_edits = CapabilityResult(supported=True, elapsedMs=int((asyncio.get_event_loop().time() - start) * 1000), note="image edit succeeded")
        except AppError as exc:
            image_edits = _failed(exc.code)
        except Exception as exc:  # noqa: BLE001
            image_edits = _failed(type(exc).__name__)

        start = asyncio.get_event_loop().time()
        try:
            await gateway.generate_image(
                ImageGenerationRequest(
                    operation=ImageOperation.GENERATION,
                    prompt="a tiny red square",
                    size="256x256",
                    request_id=uuid4(),
                )
            )
            image_generations = CapabilityResult(supported=True, elapsedMs=int((asyncio.get_event_loop().time() - start) * 1000), note="generation succeeded")
        except AppError as exc:
            image_generations = _failed(exc.code)
        except Exception as exc:  # noqa: BLE001
            image_generations = _failed(type(exc).__name__)

        return ProviderCapabilities(
            chatMultimodal=chat_multimodal,
            chatJsonSchema=chat_json_schema,
            chatJsonOnly=chat_json_only,
            imageEdits=image_edits,
            imageGenerations=image_generations,
        )

    return asyncio.run(probe_all())


def _placeholder_analysis() -> Any:
    from pelican_town_specials.domain.dish import DishAnalysis, SemanticIngredient
    return DishAnalysis(
        recognizedDish="placeholder",
        summary="placeholder",
        semanticIngredients=[
            SemanticIngredient(name="x", normalizedName="x", visibleConfidence=0.5)
        ],
        confidence=0.5,
    )


def main() -> None:
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    capabilities = _run_probe()
    _OUTPUT_PATH.write_text(
        capabilities.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
