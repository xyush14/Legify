"""Register the Headnote sales agent with Bolna's API.

Idempotent: if an agent named "Headnote Sales Agent — v1" already exists,
this script PATCHes it instead of creating a duplicate.

Reads from env (loaded via headnote.env_loader if present, else os.environ):
  BOLNA_API_KEY              required — your Bolna API key
  BOLNA_WEBHOOK_SECRET       required for prod — shared secret for tool auth
  HEADNOTE_BASE_URL          required — public base URL where the FastAPI app
                             is deployed (Bolna will POST tool calls here)
  HEADNOTE_VOICE_NAME        defaults to "Anjali"
  HEADNOTE_ADVOCATE_NAME     defaults to "Senior Advocate"
  HEADNOTE_ADVOCATE_TAGLINE  defaults to "senior advocate at the High Court"
  HEADNOTE_FOUNDER_NAME      defaults to "Ayush"
  HEADNOTE_MONTHLY_PRICE     defaults to "999"
  HEADNOTE_ANNUAL_PRICE      defaults to "9999"
  HEADNOTE_PRICE_LOWER_BY    defaults to "60"

Writes:
  BOLNA_AGENT_ID back to .env (replaces or appends)
  Prints the agent_id to stdout

Run:
  python3 scripts/push_bolna_agent.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = ROOT / "docs" / "bolna_agent_prompt.md"
ENV_FILE = ROOT / ".env"
AGENT_NAME = "Ritika — Headnote Sales"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the script works without python-dotenv."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv(ENV_FILE)


BOLNA_API_KEY = os.environ.get("BOLNA_API_KEY", "")
BOLNA_API_BASE = os.environ.get("BOLNA_API_BASE", "https://api.bolna.ai").rstrip("/")
BOLNA_WEBHOOK_SECRET = os.environ.get("BOLNA_WEBHOOK_SECRET", "")
HEADNOTE_BASE_URL = os.environ.get("HEADNOTE_BASE_URL", "https://api.headnote.ai").rstrip("/")

PLACEHOLDERS = {
    "{VOICE_NAME}":       os.environ.get("HEADNOTE_VOICE_NAME", "Anjali"),
    "{ADVOCATE_NAME}":    os.environ.get("HEADNOTE_ADVOCATE_NAME", "Senior Advocate"),
    "{ADVOCATE_TAGLINE}": os.environ.get("HEADNOTE_ADVOCATE_TAGLINE", "senior advocate at the High Court"),
    "{FOUNDER_NAME}":     os.environ.get("HEADNOTE_FOUNDER_NAME", "Ayush"),
    "{MONTHLY_PRICE}":    os.environ.get("HEADNOTE_MONTHLY_PRICE", "999"),
    "{ANNUAL_PRICE}":     os.environ.get("HEADNOTE_ANNUAL_PRICE", "9999"),
    "{PRICE_LOWER_BY}":   os.environ.get("HEADNOTE_PRICE_LOWER_BY", "60"),
}


def extract_prompt(path: Path) -> str:
    """Pull the system prompt out of the first fenced code block in the doc."""
    text = path.read_text()
    match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    if not match:
        sys.exit(f"No fenced code block found in {path}")
    prompt = match.group(1).strip()
    for placeholder, value in PLACEHOLDERS.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def build_payload(system_prompt: str) -> dict:
    api_token_header = f"Bearer {BOLNA_WEBHOOK_SECRET}" if BOLNA_WEBHOOK_SECRET else ""
    voice = PLACEHOLDERS["{VOICE_NAME}"]

    welcome = (
        f"Namaskar! Main {voice} bol rahi hoon Headnote se. "
        "Case research ke ek naye tool ke baare mein baat karna chahti thi. "
        "Kya aap 2 minute baat kar sakte hain?"
    )

    tools = [
        {
            "name": "book_demo",
            "key": "custom_task",
            "description": (
                f"Book a 15-minute demo with {PLACEHOLDERS['{ADVOCATE_NAME}']}. "
                "Use only when the lawyer agrees to a demo call."
            ),
            "pre_call_message": "Bilkul, demo set kar rahi hoon abhi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Lawyer's full name"},
                    "phone": {"type": "string", "description": "Phone number in +91XXXXXXXXXX format"},
                    "when_preference": {"type": "string", "description": "Preferred time, e.g. 'kal subah' or 'Friday 5pm'"},
                },
                "required": ["name", "phone", "when_preference"],
            },
        },
        {
            "name": "send_whatsapp",
            "key": "custom_task",
            "description": "Send a WhatsApp message: demo video, brief overview, pricing sheet, or trial activation link.",
            "pre_call_message": "WhatsApp pe bhej rahi hoon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Phone number with +91 prefix"},
                    "template": {
                        "type": "string",
                        "enum": ["demo", "overview", "pricing", "trial"],
                        "description": "Which message template to send",
                    },
                },
                "required": ["phone", "template"],
            },
        },
        {
            "name": "start_trial",
            "key": "custom_task",
            "description": "Start the 14-day free trial. Sends activation link via WhatsApp.",
            "pre_call_message": "Trial start kar rahi hoon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Phone with +91 prefix"},
                    "name": {"type": "string", "description": "Lawyer's name (optional)"},
                },
                "required": ["phone"],
            },
        },
        {
            "name": "mark_dnd",
            "key": "custom_task",
            "description": "Add the lawyer to do-not-call list. Use only after a clear no.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "enum": ["not_interested", "wrong_person", "hostile", "out_of_market", "duplicate"],
                    },
                },
                "required": ["phone", "reason"],
            },
        },
    ]

    tools_params = {
        "book_demo": {
            "method": "POST",
            "url": f"{HEADNOTE_BASE_URL}/api/bolna/tools/book_demo",
            "api_token": api_token_header,
            "param": json.dumps({
                "name": "%(name)s",
                "phone": "%(phone)s",
                "when_preference": "%(when_preference)s",
            }),
        },
        "send_whatsapp": {
            "method": "POST",
            "url": f"{HEADNOTE_BASE_URL}/api/bolna/tools/send_whatsapp",
            "api_token": api_token_header,
            "param": json.dumps({"phone": "%(phone)s", "template": "%(template)s"}),
        },
        "start_trial": {
            "method": "POST",
            "url": f"{HEADNOTE_BASE_URL}/api/bolna/tools/start_trial",
            "api_token": api_token_header,
            "param": json.dumps({"phone": "%(phone)s", "name": "%(name)s"}),
        },
        "mark_dnd": {
            "method": "POST",
            "url": f"{HEADNOTE_BASE_URL}/api/bolna/tools/mark_dnd",
            "api_token": api_token_header,
            "param": json.dumps({"phone": "%(phone)s", "reason": "%(reason)s"}),
        },
    }

    return {
        "agent_config": {
            "agent_name": AGENT_NAME,
            "agent_welcome_message": welcome,
            "webhook_url": f"{HEADNOTE_BASE_URL}/api/bolna/webhook",
            "tasks": [
                {
                    "task_type": "conversation",
                    "tools_config": {
                        "llm_agent": {
                            "agent_type": "simple_llm_agent",
                            "agent_flow_type": "streaming",
                            "llm_config": {
                                "provider": "openai",
                                "family": "openai",
                                "model": "gpt-4.1-mini",
                                "max_tokens": 220,
                                "temperature": 0.4,
                                "top_p": 0.9,
                            },
                        },
                        "synthesizer": {
                            # Sarvam = Indian-AI-native TTS, bulbul:v2 explicitly
                            # supports Hindi (hi-IN). "Anushka" is the recommended
                            # young female voice for Hinglish sales tone.
                            "provider": "sarvam",
                            "provider_config": {
                                "voice": "Anushka",
                                "voice_id": "anushka",
                                "model": "bulbul:v2",
                                "language": "hi",
                            },
                            "stream": True,
                            "buffer_size": 250,
                            "audio_format": "wav",
                        },
                        "transcriber": {
                            "provider": "deepgram",
                            "model": "nova-3",
                            # nova-3 doesn't support "multi"; for Hinglish use nova-2.
                            # Starting with "en" — most lawyers handle English; switch
                            # to nova-2 + language="multi" in the dashboard after the
                            # first team test if Hindi-only lawyers are in the mix.
                            "language": "en",
                            "stream": True,
                            "sampling_rate": 16000,
                            "encoding": "linear16",
                            # 800ms endpointing — Indian speakers pause mid-sentence;
                            # default 250ms would cut them off.
                            "endpointing": 800,
                        },
                        "input": {"provider": "plivo", "format": "wav"},
                        "output": {"provider": "plivo", "format": "wav"},
                        "api_tools": {"tools": tools, "tools_params": tools_params},
                    },
                    "toolchain": {
                        # Standard voice-agent pipeline: speech → text → reasoning → speech.
                        "execution": "parallel",
                        "pipelines": [["transcriber", "llm", "synthesizer"]],
                    },
                    "task_config": {
                        "hangup_after_silence": 12,
                        "incremental_delay": 400,
                        "number_of_words_for_interruption": 2,
                        "hangup_after_LLMCall": False,
                        "backchanneling": True,
                        "call_terminate": 240,
                    },
                }
            ],
        },
        "agent_prompts": {
            "task_1": {"system_prompt": system_prompt},
        },
    }


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {BOLNA_API_KEY}",
        "Content-Type": "application/json",
    }


def find_existing_agent(name: str) -> str | None:
    """Returns agent_id if an agent with this name already exists, else None."""
    resp = httpx.get(f"{BOLNA_API_BASE}/v2/agent/all", headers=_auth_headers(), timeout=15.0)
    if resp.status_code >= 300:
        print(f"  (could not list agents: {resp.status_code}; proceeding to create)")
        return None
    for agent in resp.json() or []:
        cfg = agent.get("agent_config") or {}
        if cfg.get("agent_name") == name:
            return agent.get("agent_id") or agent.get("id")
    return None


def _write_agent_id_to_env(agent_id: str) -> None:
    env_text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    new_line = f"BOLNA_AGENT_ID={agent_id}"
    if re.search(r"^BOLNA_AGENT_ID=.*$", env_text, flags=re.M):
        env_text = re.sub(r"^BOLNA_AGENT_ID=.*$", new_line, env_text, flags=re.M)
    else:
        if env_text and not env_text.endswith("\n"):
            env_text += "\n"
        env_text += new_line + "\n"
    ENV_FILE.write_text(env_text)


def main() -> None:
    if not BOLNA_API_KEY:
        sys.exit("BOLNA_API_KEY not set in env / .env")
    if not BOLNA_WEBHOOK_SECRET:
        print("WARN: BOLNA_WEBHOOK_SECRET not set — tool endpoints will accept any caller (DEV ONLY).")

    prompt = extract_prompt(PROMPT_FILE)
    payload = build_payload(prompt)

    print(f"\nHeadnote × Bolna agent push")
    print(f"  Bolna API base:    {BOLNA_API_BASE}")
    print(f"  Tool webhook base: {HEADNOTE_BASE_URL}")
    print(f"  Voice:             {PLACEHOLDERS['{VOICE_NAME}']}")
    print(f"  Advocate (in prompt): {PLACEHOLDERS['{ADVOCATE_NAME}']}")
    print(f"  Prompt length:     {len(prompt)} chars")
    print(f"  Tools:             {len(payload['agent_config']['tasks'][0]['tools_config']['api_tools']['tools'])}")

    # Prefer the agent_id pinned in .env (so we update THIS agent even if
    # we renamed it). Fall back to name lookup, then to create.
    existing = os.environ.get("BOLNA_AGENT_ID") or find_existing_agent(AGENT_NAME)
    if existing:
        print(f"\nUpdating existing agent id={existing}...")
        resp = httpx.put(
            f"{BOLNA_API_BASE}/v2/agent/{existing}",
            headers=_auth_headers(),
            json=payload,
            timeout=30.0,
        )
        action = "updated"
    else:
        print(f"\nCreating new agent '{AGENT_NAME}'...")
        resp = httpx.post(
            f"{BOLNA_API_BASE}/v2/agent",
            headers=_auth_headers(),
            json=payload,
            timeout=30.0,
        )
        action = "created"

    if resp.status_code >= 300:
        print(f"\n✗ Bolna API rejected the request:")
        print(f"  status: {resp.status_code}")
        print(f"  body:   {resp.text[:2000]}")
        sys.exit(1)

    data = resp.json()
    agent_id = data.get("agent_id") or data.get("id") or existing
    if not agent_id:
        print(f"\n? Response did not contain agent_id. Full response:\n{json.dumps(data, indent=2)}")
        sys.exit(1)

    _write_agent_id_to_env(agent_id)
    print(f"\n✓ Agent {action}: {agent_id}")
    print(f"✓ BOLNA_AGENT_ID written to {ENV_FILE.relative_to(ROOT)}")
    print("\nNext:")
    print("  1. Buy/connect a phone number in the Bolna dashboard (Indian outbound)")
    print("  2. Make sure HEADNOTE_BASE_URL is reachable from the public internet")
    print(f"     (current: {HEADNOTE_BASE_URL} — use ngrok or deploy for local testing)")
    print("  3. Run a test dial:")
    print("     curl -X POST http://localhost:8000/api/bolna/dial \\")
    print("       -H 'Content-Type: application/json' \\")
    print('       -d \'{"phone":"+91XXXXXXXXXX","name":"Test","practice_area":"criminal","city":"Bhopal","source":"team_test"}\'')


if __name__ == "__main__":
    main()
