import asyncio
import json
import logging
import os
import uuid
import warnings

from aiohttp import web, WSMsgType
from clients.bedrock_client import BedrockInteractClient
from s2s_events import S2sEvent
from integration.strands_agent import StrandsAgent

LOGLEVEL = os.environ.get("LOGLEVEL", "INFO").upper()
logging.basicConfig(
    level=LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=DeprecationWarning)

STRANDS_AGENT = None
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


async def health_check(request):
    tiers = STRANDS_AGENT.available_tiers() if STRANDS_AGENT else []
    tools = STRANDS_AGENT.available_tools_info() if STRANDS_AGENT else []
    return web.json_response({"status": "healthy", "strands_tiers": tiers, "strands_tools": tools})


async def websocket_handler(request):
    ws = web.WebSocketResponse(max_msg_size=0)
    await ws.prepare(request)

    session_id = str(uuid.uuid4())[:8]
    log = logging.getLogger(f"WS[{session_id}]")
    log.info("Connection opened")

    bedrock = BedrockInteractClient(model_id="amazon.nova-2-sonic-v1:0", region=AWS_REGION)
    stream = None
    is_active = False
    response_task = None
    audio_task = None
    audio_queue = asyncio.Queue()

    prompt_name = None
    audio_content_name = None
    tool_use_content = ""
    tool_use_id = ""
    tool_name = ""
    strands_tier = "sonnet"

    async def process_audio():
        nonlocal is_active
        while is_active:
            try:
                data = await audio_queue.get()
                audio_event = S2sEvent.audio_input(data["pn"], data["cn"], data["audio"])
                await bedrock.send_event(stream, audio_event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Audio error: %s", e)

    async def process_responses():
        nonlocal is_active, tool_use_content, tool_use_id, tool_name
        while is_active:
            try:
                output = await stream.await_output()
                result = await output[1].receive()

                if result.value and result.value.bytes_:
                    response_data = result.value.bytes_.decode("utf-8")
                    json_data = json.loads(response_data)

                    if "event" in json_data:
                        event_name = list(json_data["event"].keys())[0]

                        if event_name == "toolUse":
                            tool_use_content = json_data["event"]["toolUse"]
                            tool_name = json_data["event"]["toolUse"]["toolName"]
                            tool_use_id = json_data["event"]["toolUse"]["toolUseId"]
                            log.info("Tool use: %s", tool_name)

                        elif event_name == "contentEnd" and json_data["event"][event_name].get("type") == "TOOL":
                            asyncio.create_task(handle_tool_use(
                                json_data["event"]["contentEnd"].get("promptName"),
                                tool_use_id, tool_name, dict(tool_use_content) if isinstance(tool_use_content, dict) else tool_use_content,
                            ))

                    try:
                        await ws.send_str(json.dumps(json_data))
                    except Exception:
                        break

            except json.JSONDecodeError as e:
                log.error("JSON error: %s", e)
            except StopAsyncIteration:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Response error: %s", e)
                break

        is_active = False

    async def send_text_to_sonic(pn, text):
        log.info("Sending text to Sonic: %s", text[:80])
        cn = str(uuid.uuid4())
        await bedrock.send_event(stream, S2sEvent.content_start_text(pn, cn, True, "USER"))
        await bedrock.send_event(stream, S2sEvent.text_input(pn, cn, text))
        await bedrock.send_event(stream, S2sEvent.content_end(pn, cn))
        log.info("Text sent to Sonic")

    async def handle_tool_use(pn, current_tool_use_id, current_tool_name, current_tool_content):
        log.info("Processing tool: %s (id=%s)", current_tool_name, current_tool_use_id)

        try:
            tn = current_tool_name.lower()
            if tn == "getdatetool" or tn == "getdateandtimetool":
                from datetime import datetime, timezone
                result = {"result": datetime.now(timezone.utc).strftime("%A, %Y-%m-%d %H:%M:%S UTC")}
            elif tn == "externalagent":
                if STRANDS_AGENT:
                    await send_text_to_sonic(pn, "Just say 'One moment please' while I process this.")
                    content = current_tool_content.get("content", "") if isinstance(current_tool_content, dict) else ""
                    if isinstance(content, str):
                        try:
                            parsed = json.loads(content)
                            content = parsed.get("query", content)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    raw = await asyncio.to_thread(
                        STRANDS_AGENT.query, content, strands_tier, session_id
                    )
                    if isinstance(raw, dict):
                        agent_text = raw.get("text", str(raw))
                        tools_called = raw.get("tools_called", [])
                    else:
                        agent_text = str(raw)
                        tools_called = []
                    result = {"result": agent_text, "tools_called": tools_called}
                else:
                    result = {"error": "agent_not_configured", "message": "Clinical agent is not available."}
            else:
                result = {"error": "unknown_tool", "message": f"Tool '{current_tool_name}' is not supported."}
        except Exception as e:
            log.error("Tool error: %s", e)
            result = {"error": "tool_execution_failed", "message": str(e)[:200]}

        if not is_active:
            log.warning("Session closed before tool result could be sent (id=%s)", current_tool_use_id)
            return

        tc = str(uuid.uuid4())
        await bedrock.send_event(stream, S2sEvent.content_start_tool(pn, tc, current_tool_use_id))
        content_str = json.dumps(result) if isinstance(result, dict) else result
        await bedrock.send_event(stream, S2sEvent.text_input_tool(pn, tc, content_str))
        await bedrock.send_event(stream, S2sEvent.content_end(pn, tc))

        try:
            tc_list = result.get("tools_called", []) if isinstance(result, dict) else []
            await ws.send_str(json.dumps({
                "event": {"toolResult": {
                    "toolUseId": current_tool_use_id,
                    "toolName": current_tool_name,
                    "toolsCalled": tc_list,
                    "result": content_str[:500],
                }}
            }))
        except Exception:
            pass

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if "body" in data:
                        data = json.loads(data["body"])

                    if data.get("type") == "authorization":
                        continue
                    if data.get("type") == "config":
                        strands_tier = data.get("strandsTier", strands_tier)
                        log.info("Config: tier=%s", strands_tier)
                        continue

                    if "event" not in data:
                        continue

                    event_type = list(data["event"].keys())[0]

                    if event_type == "sessionStart":
                        if stream:
                            await bedrock.close_stream(stream)
                        if response_task and not response_task.done():
                            response_task.cancel()
                        if audio_task and not audio_task.done():
                            audio_task.cancel()

                        stream = await bedrock.create_stream()
                        is_active = True
                        audio_task = asyncio.create_task(process_audio())
                        response_task = asyncio.create_task(process_responses())
                        log.info("Session started, stream ready")

                        await bedrock.send_event(stream, data)

                    elif event_type == "sessionEnd":
                        if stream:
                            await bedrock.send_event(stream, data)
                            await bedrock.close_stream(stream)
                            stream = None
                        is_active = False
                        break

                    elif event_type == "audioInput" and stream and is_active:
                        ai = data["event"]["audioInput"]
                        audio_queue.put_nowait({
                            "pn": ai["promptName"],
                            "cn": ai["contentName"],
                            "audio": ai["content"],
                        })

                    elif stream and is_active:
                        if event_type == "promptStart":
                            prompt_name = data["event"]["promptStart"]["promptName"]
                        elif event_type == "contentStart" and data["event"]["contentStart"].get("type") == "AUDIO":
                            audio_content_name = data["event"]["contentStart"].get("contentName")

                        await bedrock.send_event(stream, data)

                except json.JSONDecodeError:
                    log.warning("Invalid JSON")
                except Exception as e:
                    log.error("Message error: %s", e, exc_info=True)

            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break

    except Exception as e:
        log.error("Handler error: %s", e)
    finally:
        is_active = False
        if audio_task and not audio_task.done():
            audio_task.cancel()
        if response_task and not response_task.done():
            response_task.cancel()
        if stream:
            await bedrock.close_stream(stream)
        if STRANDS_AGENT:
            STRANDS_AGENT.cleanup_session(session_id)
        log.info("Connection closed")

    return ws


async def create_app():
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    app.router.add_get("/interact-s2s", websocket_handler)
    return app


async def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))

    if os.getenv("ENABLE_STRANDS_AGENT", "true").lower() == "true":
        logger.info("Initializing Strands agent...")
        try:
            global STRANDS_AGENT
            STRANDS_AGENT = StrandsAgent()
            logger.info("Strands agent ready: %s", STRANDS_AGENT.available_tiers())
        except Exception as e:
            logger.error("Failed to init Strands agent: %s", e)

    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Server started on http://%s:%s", host, port)
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except Exception as e:
        logger.error("Server error: %s", e, exc_info=True)
