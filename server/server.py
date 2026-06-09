"""
Browser Use MCP Server

This module implements an MCP (Model-Control-Protocol) server for browser automation
using the browser_use library. It provides functionality to interact with a browser instance
via an async task queue, allowing for long-running browser tasks to be executed asynchronously
while providing status updates and results.

The server supports Server-Sent Events (SSE) for web-based interfaces.
"""

# Standard library imports
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict
from contextlib import asynccontextmanager

# Third-party imports
import mcp.types as types
import uvicorn
from dotenv import load_dotenv

# Browser-use library imports
from browser_use import Agent, Browser
from langchain_core.language_models import BaseLanguageModel
from langchain_openai import ChatOpenAI

# MCP server components
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from pythonjsonlogger import jsonlogger
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response

# Configure logging
logger = logging.getLogger()
logger.handlers = []
handler = logging.StreamHandler(sys.stderr)
formatter = jsonlogger.JsonFormatter(
    '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

def parse_bool_env(env_var: str, default: bool = False) -> bool:
    value = os.environ.get(env_var)
    if value is None:
        return default
    return value.lower() in ("true", "yes", "1", "y", "on")

def init_configuration() -> Dict[str, Any]:
    return {
        "DEFAULT_TASK_EXPIRY_MINUTES": int(os.environ.get("TASK_EXPIRY_MINUTES", 60)),
        "CLEANUP_INTERVAL_SECONDS": int(os.environ.get("CLEANUP_INTERVAL_SECONDS", 3600)),
        "MAX_AGENT_STEPS": int(os.environ.get("MAX_AGENT_STEPS", 15)),
        "PATIENT_MODE": parse_bool_env("PATIENT", False),
        "BOOKING_URL": "https://www.solacegrove.org/book-appointment"
    }

CONFIG = init_configuration()
task_store: Dict[str, Dict[str, Any]] = {}

async def run_browser_task_async(
    task_id: str,
    url: str,
    action: str,
    llm: BaseLanguageModel,
) -> None:
    browser = None
    try:
        task_store[task_id]["status"] = "running"
        task_store[task_id]["start_time"] = datetime.now().isoformat()
        
        browser = Browser()
        agent = Agent(
            task=f"Navigate to {url} and then: {action}",
            llm=llm,
            browser=browser,
        )

        agent_result = await agent.run(max_steps=CONFIG["MAX_AGENT_STEPS"])
        
        task_store[task_id]["status"] = "completed"
        task_store[task_id]["end_time"] = datetime.now().isoformat()
        task_store[task_id]["result"] = {
            "final_result": agent_result.final_result(),
            "success": agent_result.is_successful(),
            "steps_taken": agent_result.number_of_steps(),
        }
    except Exception as e:
        logger.error(f"Error in async task {task_id}: {str(e)}")
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["error"] = str(e)
    finally:
        if browser:
            await browser.close()

async def cleanup_old_tasks():
    while True:
        await asyncio.sleep(CONFIG["CLEANUP_INTERVAL_SECONDS"])
        now = datetime.now()
        to_delete = []
        for tid, data in task_store.items():
            if "created_at" in data:
                created_at = datetime.fromisoformat(data["created_at"])
                if (now - created_at).total_seconds() > CONFIG["DEFAULT_TASK_EXPIRY_MINUTES"] * 60:
                    to_delete.append(tid)
        for tid in to_delete:
            del task_store[tid]

def create_mcp_server(llm: BaseLanguageModel) -> Server:
    mcp_server = Server("solacegrove_mcp")

    @mcp_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        logger.info("RetellAI requested tool list")
        return [
            types.Tool(
                name="check_availability",
                description="Check appointment availability at Solace Grove Behavioral Health",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "date_range": {"type": "string", "description": "The date range to check (e.g., 'next week')"}
                    }
                },
            ),
            types.Tool(
                name="book_appointment",
                description="Book an appointment at Solace Grove Behavioral Health",
                inputSchema={
                    "type": "object",
                    "required": ["client_name", "client_email", "appointment_time"],
                    "properties": {
                        "client_name": {"type": "string"},
                        "client_email": {"type": "string"},
                        "appointment_time": {"type": "string", "description": "Desired date and time"}
                    }
                },
            ),
            types.Tool(
                name="browser_use",
                description="Generic browser automation tool",
                inputSchema={
                    "type": "object",
                    "required": ["url", "action"],
                    "properties": {
                        "url": {"type": "string"},
                        "action": {"type": "string"}
                    }
                },
            ),
            types.Tool(
                name="browser_get_result",
                description="Get the result of an asynchronous browser task",
                inputSchema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"}
                    }
                },
            )
        ]

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        task_id = str(uuid.uuid4())
        url = CONFIG["BOOKING_URL"]
        action = ""

        if name == "check_availability":
            date_range = arguments.get("date_range", "as soon as possible")
            action = f"Check availability for appointments in the range: {date_range}. List all available slots."
        elif name == "book_appointment":
            action = f"Book appointment for {arguments['client_name']} ({arguments['client_email']}) at {arguments['appointment_time']}."
        elif name == "browser_use":
            url = arguments["url"]
            action = arguments["action"]
        elif name == "browser_get_result":
            tid = arguments["task_id"]
            return [types.TextContent(type="text", text=json.dumps(task_store.get(tid, {"error": "Not found"}), indent=2))]
        else:
            raise ValueError(f"Unknown tool: {name}")

        task_store[task_id] = {
            "id": task_id, "status": "pending", "url": url, "action": action, "created_at": datetime.now().isoformat()
        }
        asyncio.create_task(run_browser_task_async(task_id, url, action, llm))

        if CONFIG["PATIENT_MODE"]:
            while task_store[task_id]["status"] in ["pending", "running"]:
                await asyncio.sleep(1)
            return [types.TextContent(type="text", text=json.dumps(task_store[task_id], indent=2))]

        return [types.TextContent(type="text", text=json.dumps({"task_id": task_id, "status": "pending"}, indent=2))]

    return mcp_server

@asynccontextmanager
async def lifespan(app: Starlette):
    cleanup_task = asyncio.create_task(cleanup_old_tasks())
    yield
    cleanup_task.cancel()

def main():
    port = int(os.environ.get("PORT", 8000))
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    mcp_app = create_mcp_server(llm)
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_app.run(streams[0], streams[1], mcp_app.create_initialization_options())

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response(status_code=202)

    starlette_app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ]
    )

    uvicorn.run(starlette_app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
