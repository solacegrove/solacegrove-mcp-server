import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

# Correct imports for browser-use 0.13.0
from browser_use.agent.service import Agent
from browser_use.browser.session import BrowserSession as Browser
from browser_use.llm.openai.chat import ChatOpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("solacegrove_custom_functions")

app = FastAPI(title="Solace Grove Custom Functions")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def run_browser_task(url: str, action: str) -> str:
    """Helper to run a browser-use task and return the result string."""
    # Use standard OpenAI model for production deployment
    # For local testing in Manus, we use the proxy
    base_url = os.environ.get("OPENAI_API_BASE")
    api_key = os.environ.get("OPENAI_API_KEY")
    
    llm = ChatOpenAI(
        model="gpt-4o",
        base_url=base_url,
        api_key=api_key
    )
    
    # Initialize Agent
    agent = Agent(
        task=f"Go to {url} and {action}",
        llm=llm,
    )
    result = await agent.run()
    
    # In 0.13.0, agent.run() returns an AgentHistoryList
    if result and hasattr(result, 'final_result'):
        return str(result.final_result())
    return str(result)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/check_availability")
async def check_availability(request: Request):
    """
    Retell Custom Function to check appointment availability.
    Expected args: {"date_range": "optional description of date range"}
    """
    try:
        body = await request.json()
        logger.info(f"Received check_availability request: {body}")
        
        # Retell sends params in "args" field
        args = body.get("args", body)
        date_range = args.get("date_range", "the next few days")
        
        booking_url = "https://www.solacegrove.org/book-appointment"
        action = f"look for available appointment slots for {date_range} and list them clearly."
        
        result = await run_browser_task(booking_url, action)
        return JSONResponse(content={"result": result})
        
    except Exception as e:
        logger.error(f"Error in check_availability: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/book_appointment")
async def book_appointment(request: Request):
    """
    Retell Custom Function to book an appointment.
    Expected args: {"client_name": "...", "client_email": "...", "appointment_time": "..."}
    """
    try:
        body = await request.json()
        logger.info(f"Received book_appointment request: {body}")
        
        args = body.get("args", body)
        name = args.get("client_name")
        email = args.get("client_email")
        time = args.get("appointment_time")
        
        if not all([name, email, time]):
            return JSONResponse(status_code=400, content={"error": "Missing required fields: client_name, client_email, appointment_time"})
            
        booking_url = "https://www.solacegrove.org/book-appointment"
        action = (
            f"book an appointment for {name} ({email}) at {time}. "
            "Navigate the booking form, select the time, and fill in the client details. "
            "Confirm the booking and report the success or any error message found on the page."
        )
        
        result = await run_browser_task(booking_url, action)
        return JSONResponse(content={"result": result})
        
    except Exception as e:
        logger.error(f"Error in book_appointment: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
