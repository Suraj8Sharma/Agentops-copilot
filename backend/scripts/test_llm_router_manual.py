#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Manual test script for D18 LLM Router.

Run this from the backend directory:
    python scripts/test_llm_router_manual.py

Tests:
1. Happy path: Groq succeeds, returns response with one log line
2. Fallback path: Simulates Groq failure, Gemini succeeds with two log lines
"""

import asyncio
import io
import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm.gemini_client import call_gemini  # noqa: E402
from app.llm.groq_client import call_groq  # noqa: E402
from app.llm.router import route_llm_call  # noqa: E402
from app.llm.types import LLMRateLimitError  # noqa: E402

# Configure logging to see log output
logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")


async def test_happy_path():
    """Test 1: Happy path - Groq succeeds."""
    print("\n" + "=" * 70)
    print("TEST 1: HAPPY PATH - Groq succeeds")
    print("=" * 70)

    try:
        response = await route_llm_call(
            prompt="Say hello in one sentence.", request_type="planning"
        )

        print("\n[OK] SUCCESS!")
        print(f"   Provider: {response.provider.value}")
        print(f"   Model: {response.model}")
        print(f"   Response: {response.text[:100]}...")
        print(f"   Tokens in: {response.tokens_in}")
        print(f"   Tokens out: {response.tokens_out}")
        print(f"   Latency: {response.latency_ms}ms")
        print(f"   Rate limited: {response.rate_limited}")
        return True
    except Exception as e:
        print(f"\n[ERR] FAILED: {type(e).__name__}: {str(e)}")
        return False


async def test_fallback_path():
    """Test 2: Fallback path - Force Groq failure, Gemini handles it."""
    print("\n" + "=" * 70)
    print("TEST 2: FALLBACK PATH - Groq fails (simulated), Gemini succeeds")
    print("=" * 70)

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = LLMRateLimitError("Groq rate limited (simulated)")

        try:
            response = await route_llm_call(
                prompt="Say hello in one sentence.", request_type="planning"
            )

            print("\n[OK] SUCCESS (via fallback)!")
            print(f"   Provider: {response.provider.value}")
            print(f"   Model: {response.model}")
            print(f"   Response: {response.text[:100]}...")
            print(f"   Tokens in: {response.tokens_in}")
            print(f"   Tokens out: {response.tokens_out}")
            print(f"   Latency: {response.latency_ms}ms")
            print("   Note: This should have come from Gemini after Groq failed")
            return True
        except Exception as e:
            print(f"\n[ERR] FAILED: {type(e).__name__}: {str(e)}")
            return False


async def test_direct_groq():
    """Test 3: Direct Groq call (bonus test)."""
    print("\n" + "=" * 70)
    print("TEST 3: DIRECT GROQ CALL")
    print("=" * 70)

    try:
        response = await call_groq(
            prompt="What is 2+2?",
        )

        print("\n[OK] Groq call succeeded!")
        print(f"   Response: {response.text}")
        print(f"   Model: {response.model}")
        print(f"   Latency: {response.latency_ms}ms")
        return True
    except Exception as e:
        print(f"\n[ERR] FAILED: {type(e).__name__}: {str(e)}")
        return False


async def test_direct_gemini():
    """Test 4: Direct Gemini call (bonus test)."""
    print("\n" + "=" * 70)
    print("TEST 4: DIRECT GEMINI CALL")
    print("=" * 70)

    try:
        response = await call_gemini(
            prompt="What is 2+2?",
        )

        print("\n[OK] Gemini call succeeded!")
        print(f"   Response: {response.text}")
        print(f"   Model: {response.model}")
        print(f"   Latency: {response.latency_ms}ms")
        return True
    except Exception as e:
        print(f"\n[ERR] FAILED: {type(e).__name__}: {str(e)}")
        return False


async def main():
    print("\n" + "=" * 70)
    print("D18 LLM ROUTER - MANUAL TEST SCRIPT")
    print("=" * 70)

    # Check environment variables
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    print("\nEnvironment Check:")
    print(f"  [+] GROQ_API_KEY set: {bool(groq_key)}")
    print(f"  [+] GEMINI_API_KEY set: {bool(gemini_key)}")
    print(f"  [+] GROQ_MODEL_DEFAULT: {os.environ.get('GROQ_MODEL_DEFAULT', 'not set')}")
    print(f"  [+] GEMINI_MODEL_DEFAULT: {os.environ.get('GEMINI_MODEL_DEFAULT', 'not set')}")

    if not (groq_key and gemini_key):
        print("\n[!] Missing API keys! Set GROQ_API_KEY and GEMINI_API_KEY in .env")
        return

    # Run tests
    results = []
    results.append(("Happy Path (Router)", await test_happy_path()))
    results.append(("Fallback Path (Router)", await test_fallback_path()))
    results.append(("Direct Groq Call", await test_direct_groq()))
    results.append(("Direct Gemini Call", await test_direct_gemini()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status}: {name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    print(f"\n{passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n[OK] All tests passed! D18 implementation is working correctly.")
    else:
        print(f"\n[!] {total_count - passed_count} test(s) failed. Check the output above.")


if __name__ == "__main__":
    asyncio.run(main())
