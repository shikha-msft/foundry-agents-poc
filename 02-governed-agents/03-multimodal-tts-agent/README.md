# 03 - Multimodal text-to-speech and speech-to-text API

This Python HTTP sample converts **text to speech** and **speech to text**
using **Foundry-deployed OpenAI-compatible audio models**. It does not use the
Azure AI Speech SDK or require a separate Speech resource.

It is a code-hosted, model-backed audio application, not a Foundry Prompt Agent
definition. It does not call `agents.create_version`, create a managed blueprint,
or automatically register itself in Agent 365.

## Architecture and boundaries

```text
PoC caller on approved network
       |
       v
FastAPI audio application (Easy Auth optional for controlled PoC)
       +-- POST /api/speech ---------> TTS model deployment
       |                                returns WAV/MP3 bytes
       +-- POST /api/transcriptions -> transcription model deployment
                                        returns text

Workload/managed identity or local Azure CLI -> Entra token -> model APIs
Application Insights (if configured) <- request/dependency telemetry
```

This sample is independent of the [04 MAF application](../04-maf-multi-agent/README.md).
It does not add audio tools to that coordinator or implement voice conversation,
real-time streaming, diarization, video/image processing or RAG over audio.
Synthesis is buffered and validated before audio is returned to the caller.

## Prerequisites

Customer infrastructure comes from customer IaC/platform teams, not this
sample. See the [full customer prerequisite matrix](../../CUSTOMER-PREREQUISITES.md).

| Prerequisite | Required state |
|---|---|
| Microsoft Foundry V2 | Existing approved resource/project, supported region and network access; not a classic hub project |
| Audio inference endpoint | An HTTPS OpenAI-compatible **resource** base URL ending `/openai/v1/`; not the project's `/api/projects/...` endpoint |
| TTS deployment | Approved audio synthesis deployment, e.g. `gpt-4o-mini-tts` where available; record its **deployment name** |
| STT deployment | Approved transcription deployment, e.g. `gpt-4o-mini-transcribe` where available; record its **deployment name** |
| Model compatibility | Both deployments support their respective `/audio/speech` and `/audio/transcriptions` v1 routes, chosen formats and voices |
| RBAC | Local developer or hosted runtime principal has **Cognitive Services OpenAI User** at the approved model account, or verified equivalent data-plane permissions |
| Providers | Existing `Microsoft.CognitiveServices`; monitoring providers if used; `Microsoft.Web` only if customer hosts this API on App Service |
| Runtime | Python 3.12 and approved dependencies; for local development, scoped Azure CLI login |
| Network/data policy | Approved host-to-model/token connectivity and caller network restrictions; consent to process any uploaded speech/personal data |
| Monitoring | Existing Application Insights configuration supplied securely if telemetry is required |
| Hosted API | Customer-provided Python HTTP hosting/configuration and package-only delivery process; no infrastructure script supplied here |
| Optional Easy Auth | Not required for controlled PoC. If selected, configure platform Easy Auth and `REQUIRE_APP_SERVICE_AUTH=true` together |

The existing Prompt/RAG chat deployment is not a substitute for either audio
deployment. Endpoint/model availability and quota must be checked in the
customer's resource.

## Files

| Path | Purpose |
|---|---|
| `audio_agent/configuration.py` | Validated endpoint/deployment/auth/limit configuration |
| `audio_agent/service.py` | Entra credential selection, model requests, bounded synthesis and response checks |
| `audio_agent/main.py` | HTTP endpoints, bounded request reading, optional auth and safe error responses |
| `.env.sample` | Local configuration template, no credentials |
| `tests/` | Offline API/SDK transport, configuration, auth, size and failure tests |
| `requirements.txt` / `requirements-dev.txt` | Runtime/development dependencies |

## Configure and run

From the PoC checkout root:

```powershell
cd .\02-governed-agents\03-multimodal-tts-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.sample .env
```

Populate this folder's `.env` before starting:

| Setting | Purpose/default |
|---|---|
| `AZURE_TENANT_ID` | Customer Entra tenant |
| `FOUNDRY_AUDIO_ENDPOINT` | Example shape: `https://<account>.openai.azure.com/openai/v1/` |
| `TTS_MODEL_DEPLOYMENT_NAME` | TTS deployment name, not a catalog model identifier |
| `STT_MODEL_DEPLOYMENT_NAME` | Transcription deployment name |
| `AZURE_CLIENT_ID` / `AZURE_FEDERATED_TOKEN_FILE` | Only for the selected user-assigned MI/workload identity path |
| `AUDIO_TIMEOUT_SECONDS` | SDK request timeout, default 60; not a whole-session wall-clock deadline |
| `MAX_AUDIO_UPLOAD_BYTES` | Default/maximum 24,000,000 bytes; may be lowered |
| `MAX_SYNTHESIS_BYTES` | Default/maximum 32,000,000 bytes; may be lowered |
| `REQUIRE_APP_SERVICE_AUTH` | Default false for controlled PoC |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional Azure Monitor export; use approved platform configuration |
| `OTEL_SERVICE_NAME` | Application telemetry service label |

Environment variables take precedence over local dotenv values. The
application does not read the root or MAF `.env`. Do not commit populated
configuration, access tokens, audio files or transcripts containing customer data.

```powershell
az login --tenant "<tenant-id>"
python -m uvicorn audio_agent.main:app --host 127.0.0.1 --port 8001
```

Use a customer-owned process/hosting configuration for remote deployment.
Example ASGI target: `audio_agent.main:app`. The default local bind is loopback;
do not change it to a public unauthenticated listener without approved controls.

## Text to speech

`POST /api/speech` accepts JSON:

```json
{
  "text": "Welcome to the governed audio proof of concept.",
  "voice": "alloy",
  "response_format": "wav"
}
```

- Text: nonblank, at most 4,096 characters.
- Voices exposed by this reference: `alloy`, `echo`, `fable`, `onyx`, `nova`,
  `shimmer`; the selected model must support the chosen voice.
- Output format: `wav` (default) or `mp3`.
- Entire JSON body: at most 32,768 bytes, including chunked bodies.
- Returns binary `audio/wav` or `audio/mpeg`, attachment name, `X-Request-ID`
  and `Cache-Control: no-store`.
- Empty, oversized or unexpected-format provider output returns a failure,
  not a success response with invalid audio.

PowerShell example:

```powershell
$body = @{
    text = "Welcome to the governed audio proof of concept."
    voice = "alloy"
    response_format = "wav"
} | ConvertTo-Json

Invoke-WebRequest -Method Post `
  -Uri http://localhost:8001/api/speech `
  -ContentType application/json `
  -Body $body `
  -OutFile .\speech.wav
```

Inform listeners that synthesized speech is AI-generated. This sample uses
standard voices and does not implement custom voice cloning.

## Speech to text

`POST /api/transcriptions` accepts **raw audio bytes**, not multipart/form-data
and not a server-side file path/URL.

| Header/query | Value |
|---|---|
| `Content-Type` | `audio/wav` (also accepts `audio/x-wav`) or `audio/mpeg` for MP3 |
| Optional `language` query | Two lowercase ISO-639-1 characters, e.g. `en`; omit to let the model detect language |
| Request size | At most configured `MAX_AUDIO_UPLOAD_BYTES`, enforced even without Content-Length |

The application checks WAV/MP3 headers, not the full codec/container structure;
the model validates decodability. Unsupported or corrupt audio must not be
treated as a successful transcription.

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8001/api/transcriptions?language=en" `
  -ContentType audio/wav `
  -InFile .\speech.wav
```

Response shape:

```json
{
  "text": "Welcome to the governed audio proof of concept.",
  "request_id": "<server-generated-request-id>"
}
```

No audio/transcript is written to server-side files by this application.
Request and response content still passes through process memory and the model
service; customer retention/privacy policy applies.

## Authentication, identity and governance

Credential selection follows the existing PoC pattern:

1. Workload Identity when `AZURE_FEDERATED_TOKEN_FILE` is configured (client ID
   required).
2. Managed Identity when a supported hosted MI endpoint is present.
3. Tenant-scoped Azure CLI credential for local testing.

The model client uses Entra tokens for
`https://cognitiveservices.azure.com/.default`, not account keys or stored
client secrets. Automatic SDK retries are disabled to avoid hidden repeated
inference; callers decide whether a failed request should be retried.

Easy Auth is optional for this controlled PoC. If enabled, the application
expects the platform-validated `X-MS-CLIENT-PRINCIPAL-ID` header. It does not
validate bearer tokens itself: do not bypass the platform perimeter or fake
the header. Without it, approved network restrictions are required.

**Agent ID / Agent 365 boundary:** direct audio model calls do not create a
Foundry managed agent identity or automatically join Prompt Agent account-wide
logging. This sample does not implement custom Agent ID token exchange or the
Agent 365 exporter. The existing MAF registration is not reused for this app.
If the customer mandates those controls for every agent, custom identity/
registration/export integration is a release blocker pending separate
implementation and validation. See the
[Agent Identity](../../agent-identity/README.md) and
[Agent 365](../../agent-365/README.md) guides.

Application Insights is enabled when its connection string is supplied.
Application logs contain fixed operation labels, status and correlation IDs,
not text, audio or provider response bodies. Do not enable SDK payload logging,
unapproved HTTP capture or sensitive-content tracing in this environment.

There is no explicit Content Safety/Prompt Shields call or transcript filtering
in this sample. Configure supported provider safeguards, approved content/
privacy policies and measured safety tests separately. "Governed" describes
the intended onboarding/control process, not a compliance certification.

## Health and error responses

| Endpoint/status | Meaning |
|---|---|
| `GET /healthz` | Process/lifespan available |
| `GET /readyz` | Configured service constructed; does not perform a model call or validate RBAC |
| 400 | Empty audio or malformed/negative Content-Length |
| 401 | App authentication required but platform principal missing |
| 413 | JSON/audio upload exceeds limit |
| 415 | Unsupported media type or mismatched WAV/MP3 header |
| 422 | Invalid synthesis fields or language query |
| 429 | Model rate limit; caller controls retry policy |
| 502 | Provider rejection/connection error or unusable response |
| 503 | Workload Entra credential acquisition failed |
| 504 | Provider SDK request timed out |

Provider bodies/messages are not returned to callers. Authentication/RBAC/
deployment errors remain visible through sanitized status/log events.
Configure host-level request/concurrency/time limits as well: bounded per-
request buffers do not provide a global concurrency or slow-upload limit.

## Validate

```powershell
python -m pytest
python -m ruff check audio_agent tests
python -m ruff format --check audio_agent tests
```

The root pipeline has a separate `ValidateAudio` job. Tests use an in-memory
HTTP transport with the real OpenAI client; they do not call Azure, acquire
tokens or create resources.

Before customer acceptance:

| Check | Expected evidence |
|---|---|
| TTS | Known sentence produces a playable WAV and MP3 with selected voice |
| STT | Synthetic recording yields the expected words; evaluate accuracy against customer thresholds |
| Round trip | Synthesized known sentence transcribes correctly, allowing expected casing/punctuation differences |
| Bounds | Invalid format/blank/oversized input rejected without model calls |
| Authorization | Correct runtime principal succeeds; revoked access fails visibly in a disposable test |
| Failure | Unsupported deployment, throttling and timeout do not produce success-shaped results |
| Privacy/monitoring | Request/dependency correlation with no audio, input text, tokens or transcript payload leakage |
| Access boundary | Optional auth mode and approved network restrictions tested |
| Governance | Owners/data consent/safety approvals recorded; mandatory Agent ID/Agent 365 gap resolved before release |

Local tests are not proof of live model availability, audible quality,
transcription accuracy, tenant consent or monitoring delivery.

## Microsoft references

- [Foundry/OpenAI v1 API](https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle)
- [Transcription quickstart](https://learn.microsoft.com/azure/foundry/openai/whisper-quickstart)
- [Text-to-speech model quickstart](https://learn.microsoft.com/azure/ai-foundry/openai/text-to-speech-quickstart)
- [Azure OpenAI RBAC](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/role-based-access-control)
