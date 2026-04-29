import json


class S2sEvent:
    DEFAULT_INFER_CONFIG = {
        "maxTokens": 4096,
        "topP": 0.9,
        "temperature": 0.7,
    }

    DEFAULT_AUDIO_INPUT_CONFIG = {
        "mediaType": "audio/lpcm",
        "sampleRateHertz": 16000,
        "sampleSizeBits": 16,
        "channelCount": 1,
        "audioType": "SPEECH",
        "encoding": "base64",
    }

    DEFAULT_AUDIO_OUTPUT_CONFIG = {
        "mediaType": "audio/lpcm",
        "sampleRateHertz": 24000,
        "sampleSizeBits": 16,
        "channelCount": 1,
        "voiceId": "tiffany",
        "encoding": "base64",
        "audioType": "SPEECH",
    }

    DEFAULT_TOOL_CONFIG = {
        "tools": [
            {
                "toolSpec": {
                    "name": "getDateTool",
                    "description": "Get the current date and time in UTC",
                    "inputSchema": {
                        "json": json.dumps(
                            {"type": "object", "properties": {}, "required": []}
                        )
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "externalAgent",
                    "description": "Handle clinical tasks including patient matching, encounter management, symptom triage, facility lookup, and nurse escalation.",
                    "inputSchema": {
                        "json": json.dumps(
                            {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The task or question to process",
                                    }
                                },
                                "required": ["query"],
                            }
                        )
                    },
                }
            },
        ]
    }

    @staticmethod
    def session_start(inference_config=None):
        if inference_config is None:
            inference_config = S2sEvent.DEFAULT_INFER_CONFIG
        return {"event": {"sessionStart": {"inferenceConfiguration": inference_config}}}

    @staticmethod
    def prompt_start(prompt_name, audio_output_config=None, tool_config=None):
        if audio_output_config is None:
            audio_output_config = S2sEvent.DEFAULT_AUDIO_OUTPUT_CONFIG
        if tool_config is None:
            tool_config = S2sEvent.DEFAULT_TOOL_CONFIG
        return {
            "event": {
                "promptStart": {
                    "promptName": prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": audio_output_config,
                    "toolUseOutputConfiguration": {"mediaType": "application/json"},
                    "toolConfiguration": tool_config,
                }
            }
        }

    @staticmethod
    def content_start_text(prompt_name, content_name):
        return {
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }

    @staticmethod
    def text_input(prompt_name, content_name, content):
        return {
            "event": {
                "textInput": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "content": content,
                }
            }
        }

    @staticmethod
    def content_end(prompt_name, content_name):
        return {
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                }
            }
        }

    @staticmethod
    def content_start_audio(prompt_name, content_name, audio_input_config=None):
        if audio_input_config is None:
            audio_input_config = S2sEvent.DEFAULT_AUDIO_INPUT_CONFIG
        return {
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "audioInputConfiguration": audio_input_config,
                }
            }
        }

    @staticmethod
    def audio_input(prompt_name, content_name, content):
        return {
            "event": {
                "audioInput": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "content": content,
                }
            }
        }

    @staticmethod
    def content_start_tool(prompt_name, content_name, tool_use_id):
        return {
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "interactive": False,
                    "type": "TOOL",
                    "role": "TOOL",
                    "toolResultInputConfiguration": {
                        "toolUseId": tool_use_id,
                        "type": "TEXT",
                        "textInputConfiguration": {"mediaType": "text/plain"},
                    },
                }
            }
        }

    @staticmethod
    def text_input_tool(prompt_name, content_name, content):
        return {
            "event": {
                "toolResult": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "content": content,
                }
            }
        }

    @staticmethod
    def prompt_end(prompt_name):
        return {"event": {"promptEnd": {"promptName": prompt_name}}}

    @staticmethod
    def session_end():
        return {"event": {"sessionEnd": {}}}
