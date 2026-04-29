# Nova Sonic 2 + Strands Agent Pattern

A production-ready reference architecture demonstrating **Amazon Nova Sonic 2** for natural speech-to-speech conversation with **Strands Agents** handling complex reasoning and tool orchestration via **Claude** (Opus 4.7 / Sonnet 4.6 / Haiku 4.5).

## Architecture

```
┌──────────────────┐    WebSocket     ┌──────────────────┐   Bidirectional   ┌──────────────────┐
│     Browser      │ ◄──────────────► │  Python Backend  │ ◄────Stream─────► │   Nova Sonic 2   │
│   (Cloudscape    │    Audio/Text    │    (aiohttp)     │                   │    (Bedrock)     │
│    React UI)     │                  │                  │                   │                  │
└──────────────────┘                  └────────┬─────────┘                   └──────────────────┘
                                               │
                                               │ Tool Handoff
                                               │ (externalAgent)
                                               ▼
                                      ┌──────────────────┐
                                      │  Strands Agent   │
                                      │  (Claude Models) │
                                      │                  │
                                      │ ┌──────────────┐ │
                                      │ │  6 Clinical  │ │
                                      │ │    Tools     │ │
                                      │ └──────────────┘ │
                                      └──────────────────┘
```

**Key design principle**: Nova Sonic sees only **one tool** (`externalAgent`). All complex orchestration — tool selection, multi-step reasoning, patient matching — is delegated to the Strands agent running Claude. This eliminates the tool selection reliability issues that occur when Sonic manages multiple tools directly.

## Features

- **Natural voice conversation** via Nova Sonic 2 bidirectional streaming
- **Hybrid architecture**: Sonic handles voice, Claude handles reasoning
- **3-model selection** from UI: Opus 4.7 (complex), Sonnet 4.6 (balanced), Haiku 4.5 (fast)
- **6 clinical tools** for healthcare intake workflow (demo)
- **Real-time tool invocation tracking** in the UI
- **Crossmodal text input** during active voice sessions (Nova 2 Sonic feature)
- **Configurable**: voice, turn detection sensitivity, system prompt — all from UI
- **Production infrastructure**: Terraform (ECS Fargate, ALB, CloudFront, Route53)

## Clinical Tools (Demo)

| Tool | Description |
|------|-------------|
| `create_encounter` | Create encounter record at call start |
| `match_patient` | Match caller to existing patient (name + DOB/phone) |
| `update_encounter` | Incrementally update encounter with symptoms, complaints |
| `triage_symptoms` | Schmitt-Thompson based acuity assessment |
| `find_hospital_location` | Find nearest facility (ED, urgent care, clinic, pharmacy) |
| `escalate_to_nurse` | Escalate to human nurse (immediate, 15min, 1hr callback) |

## Prerequisites

- **Python 3.12+** with pip
- **Node.js 18+** with npm
- **AWS credentials** with Bedrock access (us-east-1)
- **Bedrock model access** enabled for: Nova Sonic 2, Claude Opus 4.7, Sonnet 4.6, Haiku 4.5
- **Terraform 1.6+** (for deployment only)

## Quick Start (Local Development)

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Ensure AWS credentials are available (env vars or ~/.aws/credentials)
export AWS_DEFAULT_REGION=us-east-1
python -u server.py
```

Backend starts on `http://localhost:8080`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend starts on `http://localhost:5173` with Vite proxy to backend.

### 3. Use

1. Open `http://localhost:5173`
2. Click **Start Streaming**
3. Allow microphone access
4. Speak naturally — Nova Sonic handles the conversation
5. When you provide clinical information (name, symptoms, etc.), the Strands agent is invoked automatically

## Configuration

All configuration is done from the UI:

- **Strands Agent Model**: Select Claude tier (Opus/Sonnet/Haiku) — changeable during session
- **Voice**: Tiffany (polyglot), Matthew, Amy, Olivia, Lupe
- **Turn Detection Sensitivity**: HIGH (1.5s) / MEDIUM (1.75s) / LOW (2.0s)
- **System Prompt**: Fully editable

## Deployment (AWS)

### Infrastructure

```bash
cd infrastructure
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

terraform init
terraform apply
```

### Build & Deploy

```bash
# Build and push backend Docker image
make push

# Deploy to ECS
make deploy

# Build and deploy frontend
make frontend-deploy
```

## Project Structure

```
├── backend/
│   ├── server.py                      # aiohttp WebSocket server
│   ├── clients/
│   │   └── bedrock_client.py          # Bedrock bidirectional stream client
│   ├── integration/
│   │   ├── strands_agent.py           # 3-tier Strands agent (Opus/Sonnet/Haiku)
│   │   └── clinical_tools.py          # 6 healthcare tools
│   ├── s2s_events.py                  # Nova Sonic event builders
│   ├── buildspec.yml                  # CodeBuild spec for ECR image
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # Cloudscape layout
│   │   ├── components/
│   │   │   └── SpeechToSpeech.tsx     # Main UI component
│   │   └── lib/
│   │       ├── WebSocketEventManager.ts
│   │       ├── AudioPlayer.ts
│   │       └── config.ts
│   └── package.json
├── infrastructure/                    # Terraform (ECS, ALB, CloudFront, Route53)
├── Makefile
└── README.md
```

## How It Works

1. **Browser** captures microphone audio, streams via WebSocket to backend
2. **Backend** relays audio to **Nova Sonic 2** via Bedrock bidirectional streaming API
3. **Nova Sonic 2** processes speech, generates responses, and calls `externalAgent` when clinical tasks are needed
4. **Backend** routes `externalAgent` calls to **Strands Agent** (running in a separate thread)
5. **Strands Agent** (Claude) selects and executes appropriate clinical tools, returns result
6. **Backend** sends tool result back to Nova Sonic, which incorporates it into the spoken response
7. **Audio response** streams back through WebSocket to browser for playback

## Related Resources

- [Nova Sonic 2 Workshop](https://catalog.workshops.aws/workshops/5238419f-1337-4e0f-8cd7-02239486c40d)
- [Strands Agents Documentation](https://strandsagents.com)
- [Amazon Nova Sonic Documentation](https://docs.aws.amazon.com/nova/latest/userguide/speech.html)

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
