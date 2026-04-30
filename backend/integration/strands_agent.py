import os
import logging
import threading
import uuid

import boto3
from strands import Agent
from strands.agent.conversation_manager.sliding_window_conversation_manager import SlidingWindowConversationManager
from strands.models import BedrockModel

from integration.clinical_tools import CLINICAL_TOOLS, CLINICAL_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

BEDROCK_MODELS = {
    "opus": "us.anthropic.claude-opus-4-7",
    "sonnet": "us.anthropic.claude-sonnet-4-6",
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}


class StrandsAgent:
    def __init__(self, region=None, tools=None, system_prompt=None):
        self.region = region or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.boto_session = boto3.Session(region_name=self.region)
        self.tools = tools or CLINICAL_TOOLS
        self.system_prompt = system_prompt or CLINICAL_SYSTEM_PROMPT
        self.models = {}

        for tier, model_id in BEDROCK_MODELS.items():
            try:
                self.models[tier] = BedrockModel(model_id=model_id, boto_session=self.boto_session)
                logger.info("Initialized %s model: %s", tier, model_id)
            except Exception as e:
                logger.warning("Failed to init %s model (%s): %s", tier, model_id, e)

        if not self.models:
            raise RuntimeError("No Bedrock models could be initialized")

        self._session_agents = {}
        self._session_locks = {}
        self._global_lock = threading.Lock()

        logger.info("StrandsAgent ready (models=%s, tools=%d)", list(self.models.keys()), len(self.tools))

    def _get_or_create_session_agent(self, session_id, tier):
        key = f"{session_id}:{tier}"
        if key not in self._session_agents:
            model = self.models.get(tier) or self.models[list(self.models.keys())[0]]
            self._session_agents[key] = Agent(
                tools=self.tools,
                model=model,
                system_prompt=self.system_prompt,
                conversation_manager=None,
            )
            self._session_locks[key] = threading.Lock()
            logger.info("Created session agent: %s", key)
        return self._session_agents[key], self._session_locks[key]

    def query(self, input_text, tier="sonnet", session_id=None):
        if session_id is None:
            session_id = "default"
        if tier not in self.models:
            tier = list(self.models.keys())[0]
            logger.warning("Requested tier not available, falling back to %s", tier)

        with self._global_lock:
            agent, lock = self._get_or_create_session_agent(session_id, tier)

        if not lock.acquire(timeout=60):
            logger.warning("[%s:%s] Lock timeout", session_id, tier)
            return '{"error": "agent_busy", "message": "The clinical agent is currently processing another request. Please wait."}'

        try:
            logger.info("[%s:%s] query: %s", session_id, tier, input_text[:300])
            result = agent(input_text)
            output = str(result)

            tools_called = []
            try:
                for block in result.message.get("content", []):
                    if "toolUse" in block:
                        tools_called.append(block["toolUse"]["name"])
            except Exception:
                pass

            logger.info("[%s:%s] result (tools=%s): %s", session_id, tier, tools_called, output[:300])
            return {"text": output, "tools_called": tools_called}
        except Exception as e:
            error_msg = str(e)
            logger.error("[%s:%s] error: %s", session_id, tier, error_msg)
            if "ValidationException" in error_msg:
                return '{"error": "model_error", "message": "The model returned a validation error. The request may be malformed."}'
            if "ThrottlingException" in error_msg:
                return '{"error": "throttled", "message": "Too many requests. Please wait a moment."}'
            if "AccessDeniedException" in error_msg:
                return '{"error": "access_denied", "message": "The model does not have access permissions."}'
            return f'{{"error": "agent_error", "message": "An error occurred: {error_msg[:200]}"}}'
        finally:
            lock.release()

    def cleanup_session(self, session_id):
        keys_to_remove = [k for k in self._session_agents if k.startswith(f"{session_id}:")]
        for key in keys_to_remove:
            del self._session_agents[key]
            if key in self._session_locks:
                del self._session_locks[key]
        if keys_to_remove:
            logger.info("Cleaned up session agents for: %s", session_id)

    def available_tiers(self):
        return list(self.models.keys())

    def available_tools_info(self):
        result = []
        for t in self.tools:
            name = getattr(t, '__name__', getattr(t, 'name', str(t)))
            doc = getattr(t, '__doc__', '') or ''
            first_line = doc.strip().split('\n')[0] if doc.strip() else ''
            result.append({"name": name, "description": first_line})
        return result

    def close(self):
        self._session_agents.clear()
        self._session_locks.clear()
