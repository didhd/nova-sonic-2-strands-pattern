import { useEffect, useRef, useState } from "react";
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import Textarea from "@cloudscape-design/components/textarea";
import Input from "@cloudscape-design/components/input";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Table from "@cloudscape-design/components/table";
import Badge from "@cloudscape-design/components/badge";
import { WebSocketEventManager } from "../lib/WebSocketEventManager";
import config from "../lib/config";
import "../styles/speech-to-speech.css";

interface ToolInfo {
  name: string;
  description: string;
}

interface ChatMessage {
  id: string;
  role: string;
  message: string;
}

interface ToolInvocation {
  id: string;
  toolName: string;
  input: string;
  timestamp: string;
  status: "running" | "done" | "error";
  routedTo?: string;
}

const VOICES = [
  { label: "Tiffany (Polyglot - All languages)", value: "tiffany" },
  { label: "Matthew (en-US, Masculine)", value: "matthew" },
  { label: "Amy (en-GB, Feminine)", value: "amy" },
  { label: "Olivia (en-AU, Feminine)", value: "olivia" },
  { label: "Lupe (es-US, Feminine)", value: "lupe" },
];

const SENSITIVITIES = [
  { label: "High (Fast response - 1.5s pause)", value: "HIGH" },
  { label: "Medium (Balanced - 1.75s pause)", value: "MEDIUM" },
  { label: "Low (Patient - 2.0s pause)", value: "LOW" },
];

const STRANDS_MODELS = [
  { label: "Claude Sonnet 4.6 — Fast + intelligent (recommended)", value: "sonnet" },
  { label: "Claude Opus 4.7 — Most capable, complex reasoning", value: "opus" },
  { label: "Claude Haiku 4.5 — Fastest, simple tasks", value: "haiku" },
];

const DEFAULT_PROMPT =
  "You are a nurse triage line assistant for AnyHealth. Be warm and reassuring.\n\n" +
  "Ask ONE question at a time. Never ask multiple things in one response.\n\n" +
  "Flow:\n" +
  "1. Greet and ask what's going on today.\n" +
  "2. Ask for their phone number. Once given → say 'One moment' → call externalAgent.\n" +
  "3. Ask for full name (first and last).\n" +
  "4. Ask for date of birth. Once given → say 'Let me look you up' → call externalAgent.\n" +
  "5. Ask about their main concern (chief complaint). Once given → call externalAgent.\n" +
  "6. Ask when it started.\n" +
  "7. Ask severity 1-10.\n" +
  "8. Ask about other symptoms. Once answered → say 'Let me check' → call externalAgent.\n" +
  "9. Share the triage result. If urgent → call externalAgent to transfer.\n\n" +
  "Rules:\n" +
  "- ONE question per response. Short sentences only.\n" +
  "- Call externalAgent at steps 2, 4, 5, 8, and 9.\n" +
  "- Always say a brief hold message before each tool call.";

export default function SpeechToSpeech() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<"stopped" | "loading" | "success" | "error">("stopped");
  const [statusText, setStatusText] = useState("Click Start to begin");
  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_PROMPT);
  const [voiceId, setVoiceId] = useState(VOICES[0]);
  const [sensitivity, setSensitivity] = useState(SENSITIVITIES[1]);
  const [strandsTier, setStrandsTier] = useState(STRANDS_MODELS[0]);
  const [textInput, setTextInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isUserThinking, setIsUserThinking] = useState(false);
  const [isAssistantThinking, setIsAssistantThinking] = useState(false);
  const [strandsTools, setStrandsTools] = useState<ToolInfo[]>([]);
  const [toolInvocations, setToolInvocations] = useState<ToolInvocation[]>([]);

  const wsRef = useRef<WebSocketEventManager | null>(null);
  const chatRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then((data) => {
        if (data.strands_tools) setStrandsTools(data.strands_tools);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, isUserThinking, isAssistantThinking]);

  useEffect(() => {
    return () => {
      wsRef.current?.cleanup();
    };
  }, []);

  useEffect(() => {
    if (!wsRef.current) return;

    const handler = ((e: CustomEvent) => {
      const data = e.detail;
      if (!data?.event) return;
      const ev = data.event;

      if (ev.contentStart) {
        if (ev.contentStart.type === "TEXT" && ev.contentStart.role === "ASSISTANT") setIsAssistantThinking(false);
        if (ev.contentStart.type === "AUDIO" && ev.contentStart.role === "USER") {
          setIsUserThinking(true);
        } else if (ev.contentStart.type === "AUDIO" && ev.contentStart.role === "ASSISTANT") {
          setIsUserThinking(false);
        }
      }

      if (ev.textOutput) {
        const { role, content } = ev.textOutput;
        const id = `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        if (role === "USER") {
          setIsUserThinking(false);
          setIsAssistantThinking(true);
        }
        setMessages((prev) => {
          if (prev.some((m) => m.role === role && m.message === content)) return prev;
          return [...prev, { id, role, message: content }];
        });
      }

      if (ev.toolUse) {
        const inv: ToolInvocation = {
          id: ev.toolUse.toolUseId || `tool-${Date.now()}`,
          toolName: ev.toolUse.toolName,
          input: ev.toolUse.content || "",
          timestamp: new Date().toLocaleTimeString(),
          status: "running",
        };
        setToolInvocations((prev) => [inv, ...prev]);
      }

      if (ev.toolResult) {
        const tid = ev.toolResult.toolUseId;
        const toolsCalled: string[] = ev.toolResult.toolsCalled || [];
        const routedTo = toolsCalled.length > 0 ? toolsCalled.join(" → ") : "info_only";

        setToolInvocations((prev) =>
          prev.map((t) => t.id === tid ? { ...t, status: "done", routedTo } : t)
        );
      }

      if (ev.contentEnd) {
        if (ev.contentEnd.type === "TOOL") {
          setToolInvocations((prev) =>
            prev.map((t) => t.status === "running" ? { ...t, status: "done" } : t)
          );
        }
        if (ev.contentEnd.type === "TEXT") {
          if (wsRef.current?.role === "ASSISTANT") setIsAssistantThinking(false);
          if (wsRef.current?.role === "USER") {
            setIsUserThinking(false);
            setIsAssistantThinking(true);
          }
        }
        if (ev.contentEnd.type === "AUDIO" && wsRef.current?.role === "USER") {
          setIsUserThinking(false);
        }
      }
    }) as EventListener;

    window.addEventListener("nova-sonic-event", handler);
    return () => window.removeEventListener("nova-sonic-event", handler);
  }, [isStreaming]);

  const handleStart = async () => {
    if (isInitializing || isStreaming) return;
    setIsInitializing(true);
    setConnectionStatus("loading");
    setStatusText("Connecting...");
    setMessages([]);
    setToolInvocations([]);

    const wsUrl = config.websocketUrl + "/interact-s2s";
    const mgr = new WebSocketEventManager(
      wsUrl,
      () => {
        setIsStreaming(false);
        setIsInitializing(false);
        setConnectionStatus("error");
        setStatusText("Disconnected");
      },
      () => setConnectionStatus("success"),
      systemPrompt
    );
    mgr.setEndpointingSensitivity(sensitivity.value as "HIGH" | "MEDIUM" | "LOW");
    mgr.setVoiceId(voiceId.value);
    mgr.setStrandsTier(strandsTier.value);
    wsRef.current = mgr;

    try {
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Connection timeout")), 10000);
        const check = () => {
          if (mgr.socket?.readyState === WebSocket.OPEN) { clearTimeout(timeout); resolve(); }
          else if (mgr.socket?.readyState === WebSocket.CLOSED) { clearTimeout(timeout); reject(new Error("Connection failed")); }
          else setTimeout(check, 100);
        };
        check();
      });
      setIsStreaming(true);
      setIsInitializing(false);
      setConnectionStatus("success");
      setStatusText("Connected — Speak to begin");
    } catch (e) {
      setIsInitializing(false);
      setConnectionStatus("error");
      setStatusText(e instanceof Error ? e.message : "Connection error");
    }
  };

  const handleStop = () => {
    wsRef.current?.cleanup();
    wsRef.current = null;
    setIsStreaming(false);
    setIsInitializing(false);
    setConnectionStatus("stopped");
    setStatusText("Click Start to begin");
    setIsUserThinking(false);
    setIsAssistantThinking(false);
  };

  const handleSendText = () => {
    if (!textInput.trim() || !wsRef.current) return;
    const text = textInput.trim();
    const id = `user-text-${Date.now()}`;
    setMessages((prev) => [...prev, { id, role: "USER", message: text }]);
    wsRef.current.sendTextInput(text);
    setTextInput("");
    setIsAssistantThinking(true);
  };

  return (
    <SpaceBetween size="l">
      <Container
        header={
          <Header
            variant="h1"
            description="Nova Sonic 2 handles natural voice conversation. Strands agents (Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5) handle complex reasoning and tool orchestration."
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="primary" onClick={handleStart} disabled={isStreaming || isInitializing} loading={isInitializing}>
                  Start Streaming
                </Button>
                <Button onClick={handleStop} disabled={!isStreaming}>
                  Stop
                </Button>
              </SpaceBetween>
            }
          >
            Speech-to-Speech with Strands Agent
          </Header>
        }
      >
        <SpaceBetween size="m">
          <Box>
            <StatusIndicator type={connectionStatus}>{statusText}</StatusIndicator>
            {isStreaming && (
              <Box margin={{ left: "m" }} display="inline-block">
                <span className={`pulse-ring ${isUserThinking ? "listening" : ""}`} />
                <Box variant="small" display="inline-block" margin={{ left: "xs" }}>
                  {isUserThinking ? "Listening..." : isAssistantThinking ? "Thinking..." : "Ready"}
                </Box>
              </Box>
            )}
          </Box>

          <ExpandableSection
            headerText={`Strands Agent Tools (${strandsTools.length})${toolInvocations.length > 0 ? ` — ${toolInvocations.length} call${toolInvocations.length > 1 ? "s" : ""}` : ""}`}
            defaultExpanded={true}
          >
            <SpaceBetween size="s">
              <Box variant="small" color="text-body-secondary">
                Nova Sonic routes to a single <Badge color="blue">externalAgent</Badge> tool.
                The Strands agent then orchestrates these tools:
              </Box>
              <Box variant="small" color="text-body-secondary" margin={{ top: "xs" }}>
                Demo patients: <strong>John Smith</strong> (DOB 1985-03-15, +14155551234, BlueCross PPO, allergic to penicillin) |{" "}
                <strong>Maria Garcia</strong> (DOB 1992-07-22, +14155555678, Aetna HMO) |{" "}
                <strong>James Wilson</strong> (DOB 1978-11-30, +14155559012, Medicare Part B, diabetes type 2)
              </Box>
              <Table
                variant="embedded"
                columnDefinitions={[
                  { id: "name", header: "Tool", cell: (item: ToolInfo) => <Badge>{item.name}</Badge>, width: 220 },
                  { id: "description", header: "Description", cell: (item: ToolInfo) => item.description },
                ]}
                items={strandsTools}
                empty={<Box textAlign="center" color="text-body-secondary">Loading tools...</Box>}
              />
              {toolInvocations.length > 0 && (
                <>
                  <Box variant="h4" margin={{ top: "m" }}>Invocation History</Box>
                  <Table
                    variant="embedded"
                    columnDefinitions={[
                      {
                        id: "status",
                        header: "Status",
                        cell: (item: ToolInvocation) => (
                          <StatusIndicator type={item.status === "running" ? "in-progress" : item.status === "done" ? "success" : "error"}>
                            {item.status === "running" ? "Running" : item.status === "done" ? "Done" : "Error"}
                          </StatusIndicator>
                        ),
                        width: 120,
                      },
                      { id: "time", header: "Time", cell: (item: ToolInvocation) => item.timestamp, width: 100 },
                      { id: "routed", header: "Routed To", cell: (item: ToolInvocation) => (
                        item.routedTo && item.routedTo !== "info_only"
                          ? <Badge color="green">{item.routedTo}</Badge>
                          : item.status === "running" ? <Badge color="grey">pending</Badge> : <Badge color="blue">info_only</Badge>
                      ), width: 280 },
                      { id: "input", header: "Input", cell: (item: ToolInvocation) => <Box variant="small">{item.input.slice(0, 120)}{item.input.length > 120 ? "..." : ""}</Box> },
                    ]}
                    items={toolInvocations}
                  />
                </>
              )}
            </SpaceBetween>
          </ExpandableSection>

          <ExpandableSection headerText="Configuration" defaultExpanded={!isStreaming}>
            <SpaceBetween size="m">
              <FormField label="System Prompt">
                <Textarea
                  value={systemPrompt}
                  onChange={({ detail }) => setSystemPrompt(detail.value)}
                  disabled={isStreaming}
                  rows={4}
                />
              </FormField>
              <FormField label="Strands Agent Model" description="Claude model used when Nova Sonic hands off complex tasks to the Strands agent">
                <Select
                  selectedOption={strandsTier}
                  onChange={({ detail }) => {
                    const opt = detail.selectedOption as typeof strandsTier;
                    setStrandsTier(opt);
                    wsRef.current?.setStrandsTier(opt.value);
                  }}
                  options={STRANDS_MODELS}
                />
              </FormField>
              <ColumnLayout columns={2}>
                <FormField label="Voice">
                  <Select
                    selectedOption={voiceId}
                    onChange={({ detail }) => setVoiceId(detail.selectedOption as typeof voiceId)}
                    options={VOICES}
                    disabled={isStreaming}
                  />
                </FormField>
                <FormField label="Turn Detection Sensitivity">
                  <Select
                    selectedOption={sensitivity}
                    onChange={({ detail }) => setSensitivity(detail.selectedOption as typeof sensitivity)}
                    options={SENSITIVITIES}
                    disabled={isStreaming}
                  />
                </FormField>
              </ColumnLayout>
            </SpaceBetween>
          </ExpandableSection>
        </SpaceBetween>
      </Container>

      <Container header={<Header variant="h2" actions={
        <Button iconName="remove" variant="icon" onClick={() => { setMessages([]); setIsUserThinking(false); setIsAssistantThinking(false); }} />
      }>Conversation</Header>}>
        <div className="chat-container" ref={chatRef}>
          {messages.length === 0 && !isUserThinking && !isAssistantThinking && (
            <Box textAlign="center" color="text-body-secondary" padding="xxl">
              <Box variant="p">Start streaming and speak to begin the conversation.</Box>
              <Box variant="small">Nova Sonic 2 provides natural voice. Strands agents handle complex tool orchestration.</Box>
            </Box>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={`chat-message ${msg.role.toLowerCase()}`}>
              <div className="chat-role">{msg.role}</div>
              <div>{msg.message}</div>
            </div>
          ))}
          {isUserThinking && (
            <div className="chat-message user">
              <div className="chat-role">USER</div>
              <div className="thinking-indicator">
                <span>Listening</span>
                <div className="thinking-dots"><span className="dot" /><span className="dot" /><span className="dot" /></div>
              </div>
            </div>
          )}
          {isAssistantThinking && (
            <div className="chat-message assistant">
              <div className="chat-role">ASSISTANT</div>
              <div className="thinking-indicator">
                <span>Thinking</span>
                <div className="thinking-dots"><span className="dot" /><span className="dot" /><span className="dot" /></div>
              </div>
            </div>
          )}
        </div>

        {isStreaming && (
          <Box margin={{ top: "m" }}>
            <div style={{ display: "flex", gap: "8px" }}>
              <div style={{ flex: 1 }}>
                <Input
                  value={textInput}
                  onChange={({ detail }) => setTextInput(detail.value)}
                  onKeyDown={({ detail }) => { if (detail.key === "Enter") handleSendText(); }}
                  placeholder="Type a message during voice session (crossmodal text input)"
                />
              </div>
              <Button onClick={handleSendText} disabled={!textInput.trim()}>Send</Button>
            </div>
          </Box>
        )}
      </Container>
    </SpaceBetween>
  );
}
