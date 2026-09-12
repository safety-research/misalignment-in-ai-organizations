#!/usr/bin/env python3
"""
LLM client using safety-tooling InferenceAPI
A cleaner, more robust wrapper around the safety-tooling package
"""

import logging
import tiktoken
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union

from safetytooling.utils import utils
from safetytooling.apis import InferenceAPI
from safetytooling.data_models import ChatMessage, MessageRole, Prompt

DEFAULT_CONFIG = {
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 20000,
    "temperature": 0.1,
    "api_type": "anthropic",
}
# Initialize conversation truncation based on max_tokens
# Use 80% for conversation, leave 20% for response generation
CONVERSATION_PERCENTAGE = 0.80
MIN_CONVERSATION_TOKENS = 2000  # Minimum floor


class SafetyToolingLLMClient:
    """LLM client using safety-tooling InferenceAPI with automatic conversation truncation"""

    def __init__(
        self,
        config_dict: Dict[str, Any] = None,
        cache_dir: Path = None,
        suppress_warnings: bool = True,
        use_cache: bool = True,
    ):
        """Initialize the safety-tooling based LLM client

        Args:
            config_dict: Configuration dictionary with model settings
            cache_dir: Directory for caching responses
            suppress_warnings: If True, suppresses safety-tooling warnings (default: True)
            use_cache: If True, uses cached responses when available (default: True)
        """
        utils.setup_environment()

        if suppress_warnings:
            logging.getLogger("safetytooling").setLevel(logging.ERROR)

        # Set default cache directory (None disables file caching when no_cache=True)
        if cache_dir is None and use_cache:
            cache_dir = Path.cwd() / ".cache"

        # Extract config values
        self.config = config_dict or DEFAULT_CONFIG
        self.model_id = self.config.get("model")
        self.temperature = self.config.get("temperature")
        self.max_tokens = self.config.get("max_tokens")
        self.use_cache = use_cache

        # Initialize the InferenceAPI
        self.api = InferenceAPI(
            print_prompt_and_response=False,
            no_cache=not use_cache,
            cache_dir=cache_dir if use_cache else None,
        )

        self.logger = logging.getLogger("safetytooling")

        calculated_max = int(self._get_context_window_for_model(self.model_id) * CONVERSATION_PERCENTAGE)
        self.conversation_max_tokens = max(calculated_max, MIN_CONVERSATION_TOKENS)

        self.logger.info(
            f"Conversation max tokens set to {self.conversation_max_tokens} "
            f"(based on {CONVERSATION_PERCENTAGE:.0%} of {self.max_tokens} tokens)"
        )

        # Initialize encoder based on model
        self.encoder = self._get_encoder_for_model(self.model_id)

    def _get_encoder_for_model(self, model_id: str) -> Optional[object]:
        """Get the appropriate tiktoken encoder for the given model"""
        if not model_id:
            return None

        try:
            model_lower = model_id.lower()

            # Modern model encoder mappings
            if "gpt" in model_lower:
                # GPT-4o and other modern GPT models use cl100k_base
                return tiktoken.get_encoding("cl100k_base")
            elif "claude" in model_lower:
                # Claude models - use cl100k_base as close approximation
                return tiktoken.get_encoding("cl100k_base")
            else:
                # Default fallback for any other models
                self.logger.info(f"Unknown model '{model_id}', using cl100k_base encoder as fallback")
                return tiktoken.get_encoding("cl100k_base")

        except Exception as e:
            self.logger.warning(f"Failed to load tiktoken encoder for model '{model_id}': {e}")
            return None

    def _get_context_window_for_model(self, _model_id: str) -> int:
        """Get the context window for the given model"""
        # All current Claude models have 200k context window
        return 200000

    def _count_tokens(self, text: str) -> int:
        """Count tokens in a text string"""
        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Rough estimate: ~4 characters per token
            return len(text) // 4

    def _count_message_tokens(self, message: Dict[str, str]) -> int:
        """Count tokens in a message dict"""
        # Account for role and content structure
        role_tokens = self._count_tokens(message.get("role", ""))
        content_tokens = self._count_tokens(message.get("content", ""))
        # Add overhead for message structure
        return role_tokens + content_tokens + 4

    def _count_conversation_tokens(self, messages: List[Dict[str, str]], system_message: Optional[str] = None) -> int:
        """Count total tokens in conversation including system message"""
        total = 0

        if system_message:
            total += self._count_tokens(system_message) + 4

        for message in messages:
            total += self._count_message_tokens(message)

        return total

    def _truncate_conversation_if_needed(
        self,
        messages: List[Dict[str, str]],
        system_message: Optional[str] = None,
        keep_first_n: int = 2,
        keep_last_n: int = 15,
        summarize_removed: bool = True,
    ) -> Tuple[List[Dict[str, str]], bool]:
        """
        Truncate conversation history to fit within token limits

        Args:
            messages: List of message dictionaries
            system_message: System message (counts toward token limit)
            keep_first_n: Number of initial messages to always keep (task description)
            keep_last_n: Number of recent messages to prioritize keeping
            summarize_removed: Whether to add a summary message about removed content

        Returns:
            Tuple of (truncated_messages, was_truncated)
        """
        current_tokens = self._count_conversation_tokens(messages, system_message)

        # If under limit, return as-is
        if current_tokens <= self.conversation_max_tokens:
            return messages.copy(), False

        # Log warning about truncation
        self.logger.warning(
            f"Conversation exceeds token limit ({current_tokens} > {self.conversation_max_tokens}). "
            f"Truncating from {len(messages)} messages..."
        )

        # Start with first N and last N messages
        truncated = []

        # Keep initial messages (task description)
        if keep_first_n > 0 and len(messages) > keep_first_n:
            truncated.extend(messages[:keep_first_n])

        # Add truncation notice
        if summarize_removed and len(messages) > keep_first_n + keep_last_n:
            removed_count = len(messages) - keep_first_n - keep_last_n
            truncation_notice = {
                "role": "user",
                "content": f"[Note: {removed_count} intermediate messages were removed to stay within token limits. The conversation continues from recent context.]",
            }
            truncated.append(truncation_notice)

        # Keep recent messages
        if keep_last_n > 0 and len(messages) > keep_last_n:
            truncated.extend(messages[-keep_last_n:])
        else:
            truncated = messages.copy()

        # If still too long, progressively remove older messages from the middle
        while self._count_conversation_tokens(truncated, system_message) > self.conversation_max_tokens:
            if len(truncated) <= keep_first_n + 2:  # Minimum viable conversation
                break

            # Remove message from middle (after first_n, before last messages)
            middle_idx = keep_first_n + 1
            if middle_idx < len(truncated) - 2:
                truncated.pop(middle_idx)
            else:
                # Start removing from the end if necessary
                truncated.pop(-3)  # Keep last 2 messages at minimum

        new_tokens = self._count_conversation_tokens(truncated, system_message)
        self.logger.info(f"Truncated to {len(truncated)} messages ({new_tokens} tokens)")

        return truncated, True

    async def generate_response(
        self,
        prompt: Union[str, List[Dict[str, str]]],
        system_message: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a response to a prompt or conversation history with automatic truncation

        Args:
            prompt: Either a string prompt or a list of conversation messages
            system_message: Optional system message
            config_override: Optional config to override default settings for this request
                           Can include: model, temperature, max_tokens
        """

        try:
            # Use override config if provided, otherwise fall back to instance config
            model_id = self.model_id
            temperature = self.temperature
            max_tokens = self.max_tokens

            if config_override:
                model_id = config_override.get("model", model_id)
                temperature = config_override.get("temperature", temperature)
                max_tokens = config_override.get("max_tokens", max_tokens)

            # Create messages
            messages = []
            if system_message:
                messages.append(ChatMessage(role=MessageRole.system, content=system_message))

            # Handle both string prompts and conversation history
            if isinstance(prompt, str):
                messages.append(ChatMessage(role=MessageRole.user, content=prompt))
            elif isinstance(prompt, list):
                # Apply conversation truncation for list prompts
                safe_conversation, _was_truncated = self._truncate_conversation_if_needed(
                    prompt, system_message, keep_first_n=2, keep_last_n=15, summarize_removed=True
                )

                # Convert truncated conversation history to ChatMessage objects
                for msg in safe_conversation:
                    if msg["role"] == "user":
                        messages.append(ChatMessage(role=MessageRole.user, content=msg["content"]))
                    elif msg["role"] == "assistant":
                        messages.append(ChatMessage(role=MessageRole.assistant, content=msg["content"]))
            else:
                raise ValueError(f"Unsupported prompt type: {type(prompt)}")

            # Create prompt object
            prompt_obj = Prompt(messages=messages)
            response = await self.api(
                model_id=model_id, prompt=prompt_obj, temperature=temperature, max_tokens=max_tokens
            )

            # Extract content from response
            # The InferenceAPI returns a list of LLMResponse objects
            if isinstance(response, list) and len(response) > 0:
                # Get the first response
                first_response = response[0]
                if hasattr(first_response, "completion") and first_response.completion:
                    return first_response.completion
                elif hasattr(first_response, "content") and first_response.content:
                    return first_response.content
                else:
                    return str(first_response)
            elif hasattr(response, "completion") and response.completion:
                return response.completion
            elif hasattr(response, "content") and response.content:
                return response.content
            else:
                return str(response)

        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            raise

    @classmethod
    def from_config_dict(
        cls, config_dict: Dict[str, Any], suppress_warnings: bool = True, use_cache: bool = True
    ) -> "SafetyToolingLLMClient":
        """Create LLM client from configuration dictionary"""
        return cls(config_dict=config_dict, suppress_warnings=suppress_warnings, use_cache=use_cache)


def create_llm_client(
    config_dict: Dict[str, Any] = None, suppress_warnings: bool = True, use_cache: bool = True
) -> SafetyToolingLLMClient:
    """Factory function to create LLM client using safety-tooling

    Args:
        config_dict: Configuration dictionary with model settings
        suppress_warnings: If True, suppresses safety-tooling warnings (default: True)
        use_cache: If True, uses cached responses when available (default: True)
    """

    return SafetyToolingLLMClient.from_config_dict(
        config_dict, suppress_warnings=suppress_warnings, use_cache=use_cache
    )
