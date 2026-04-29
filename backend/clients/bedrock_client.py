import json
import logging
import os
import warnings

from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.models import (
    InvokeModelWithBidirectionalStreamInputChunk,
    BidirectionalInputPayloadPart,
)
from aws_sdk_bedrock_runtime.config import Config
from smithy_aws_core.auth.sigv4 import SigV4AuthScheme
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver

warnings.filterwarnings("ignore", category=DeprecationWarning)
logger = logging.getLogger(__name__)


class BedrockInteractClient:
    def __init__(self, model_id="amazon.nova-2-sonic-v1:0", region="us-east-1"):
        self.model_id = model_id
        self.region = region
        self.bedrock_client = None
        logger.info("BedrockInteractClient [model_id=%s, region=%s]", model_id, region)

    def _ensure_env_credentials(self):
        if os.environ.get("AWS_ACCESS_KEY_ID"):
            return
        try:
            import boto3
            session = boto3.Session()
            creds = session.get_credentials()
            if creds:
                frozen = creds.get_frozen_credentials()
                os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
                os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
                if frozen.token:
                    os.environ["AWS_SESSION_TOKEN"] = frozen.token
                logger.info("Loaded credentials from boto3 default chain")
        except Exception as e:
            logger.error("Failed to load boto3 credentials: %s", e)

    def initialize_client(self):
        if self.bedrock_client is not None:
            return True

        self._ensure_env_credentials()

        try:
            config = Config(
                endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
                region=self.region,
                aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
                auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="bedrock")},
            )
            self.bedrock_client = BedrockRuntimeClient(config=config)
            logger.info("Bedrock client initialized")
            return True
        except Exception as e:
            logger.error("Failed to initialize Bedrock client: %s", e, exc_info=True)
            return False

    async def create_stream(self):
        if not self.bedrock_client:
            if not self.initialize_client():
                raise Exception("Failed to initialize Bedrock client")

        stream = await self.bedrock_client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        logger.info("Stream created")
        return stream

    async def send_event(self, stream, event_data):
        try:
            event_json = json.dumps(event_data)
            event = InvokeModelWithBidirectionalStreamInputChunk(
                value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
            )
            await stream.input_stream.send(event)
            return True
        except Exception as e:
            logger.error("Error sending event: %s", e)
            return False

    async def close_stream(self, stream):
        try:
            if stream:
                await stream.input_stream.close()
                return True
        except Exception as e:
            logger.error("Error closing stream: %s", e)
        return False
