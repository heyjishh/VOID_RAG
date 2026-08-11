from __future__ import annotations
from functools import lru_cache
import litellm
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from app.config.settings import settings


class LiteLLMChat(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "litellm"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("Use async")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        lc_msgs = [
            {
                "role": "user" if m.type == "human" else ("assistant" if m.type == "ai" else m.type),
                "content": m.content,
            }
            for m in messages
        ]
        chain = settings.llm_provider_chain
        last_exc = None
        for provider in chain:
            try:
                resp = await litellm.acompletion(
                    model=provider["model"],
                    messages=lc_msgs,
                    api_key=provider["api_key"] or None,
                    api_base=provider.get("api_base"),  # None for direct providers
                )
                text = resp.choices[0].message.content
                # Surface which provider in the fallback chain actually served this
                # request — otherwise silently discarded once acompletion returns.
                model_provider, _, model_name = provider["model"].partition("/")
                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                content=text,
                                response_metadata={
                                    "model_provider": model_provider,
                                    "model_name": model_name or provider["model"],
                                },
                            )
                        )
                    ]
                )
            except Exception as exc:
                last_exc = exc
                continue
        raise RuntimeError(f"All LLM providers failed. Last error: {last_exc}")


@lru_cache(maxsize=1)
def get_llm() -> LiteLLMChat:
    return LiteLLMChat()
