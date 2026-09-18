import sys
import time

import httpx

BASE_URL = "http://127.0.0.1:8000"


def run_test():
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        print("1. Authenticating test user...")

        # Read from environment or use a default that might need to be changed if email confirmations are ON  # noqa: E501
        import os

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        email = os.getenv("TEST_EMAIL", "your.real.email@gmail.com")
        password = os.getenv("TEST_PASSWORD", "AgentOps2026!")

        print(f"   Using email: {email} (Edit script or set TEST_EMAIL env var to change)")

        # Try to login first, if it fails, try to sign up
        try:
            resp = client.post("/auth/login", json={"email": email, "password": password})
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [400, 401]:
                print("   Login failed, attempting signup...")
                resp = client.post("/auth/signup", json={"email": email, "password": password})
                resp.raise_for_status()
            else:
                raise
        token = resp.json()["access_token"]
        print("   [Success] Got JWT Token.")

        # Let user choose what to test, or default to a schedule request
        raw_input = "send an email to my boss"
        if len(sys.argv) > 1:
            raw_input = " ".join(sys.argv[1:])

        print(f"\n2. Submitting Task: '{raw_input}'")
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post(
            "/tasks", json={"input_type": "text", "raw_input": raw_input}, headers=headers
        )  # noqa: E501
        resp.raise_for_status()

        task = resp.json()
        task_id = task["id"]
        print(f"   [Success] Created Task ID: {task_id}")

        print("\n3. Polling Task Status (watch your uvicorn logs to see the LLM planner!)...")
        for _ in range(15):
            time.sleep(2)
            resp = client.get(f"/tasks/{task_id}", headers=headers)
            current_status = resp.json()["status"]
            print(f"   Status: {current_status}")
            if current_status in ["completed", "failed", "awaiting_approval"]:
                break

        print(
            "\nTest finished! If it reached 'awaiting_approval' or 'completed', the LLM successfully created the plan."
        )  # noqa: E501
        print(
            "Check your Supabase Dashboard (tables: tasks, task_plans, execution_logs, llm_usage_logs) to see the results!"
        )  # noqa: E501


if __name__ == "__main__":
    run_test()
