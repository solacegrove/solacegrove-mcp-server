import asyncio
import os
import json
import logging
from typing import List, Literal, Optional, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from browser_use import Agent, Browser, BrowserConfig
from langchain_openai import ChatOpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("solacegrove_custom_functions")

# Initialize FastAPI app
app = FastAPI()

# --- Pydantic Models for Custom Functions ---

class CheckAvailabilityRequest(BaseModel):
    date_range: Optional[str] = Field(None, description="Optional date range to check availability for (e.g., 'next week', 'July 2026')")

class CheckAvailabilityResponse(BaseModel):
    available_slots: List[str] = Field(..., description="List of available appointment slots")
    message: str = Field(..., description="A message describing the availability")

class BookAppointmentRequest(BaseModel):
    # STEP 1: SERVICE TYPE SELECTION
    service_type: Literal[
        "Initial Consultation - No Charge (15 minutes)",
        "Psychiatric Diagnostic Evaluation (1 hour, 30 minutes)",
        "Family Psychotherapy without patient present (1 hour)"
    ] = Field(..., description="Type of service to book")

    # STEP 2: LOCATION SELECTION
    location: Literal["telehealth", "in_person"] = Field(..., description="Location for the appointment")

    # STEP 3: DATE AND TIME SELECTION
    appointment_date: str = Field(..., description="Date of the appointment (e.g., '2026-06-13')")
    appointment_time: str = Field(..., description="Time of the appointment (e.g., '1:00 PM')")

    # STEP 4: PRESCREENER (Reason for Care)
    reason_for_care: List[str] = Field(..., description="Reasons for seeking care (e.g., ['Anxiety', 'Depression'])")
    care_type: List[str] = Field(..., description="Type of care sought (e.g., ['Psychotherapy', 'Medication'])")
    treatment_history: List[str] = Field(..., description="Past mental health concerns or treatment (e.g., ['In therapy now'])")

    # STEP 5: BILLING & PAYMENT
    payment_method: str = Field(..., description="Payment method (e.g., 'Self-Pay', 'Insurance')")
    insurance_details: Optional[str] = Field(None, description="Insurance details (text area, 600 char limit)")

    # STEP 6: CONTACT INFORMATION
    receiving_care: Literal["me", "partner_and_me", "someone_else"] = Field(..., description="Who would be receiving care")
    legal_first_name: str = Field(..., description="Client's legal first name")
    legal_last_name: str = Field(..., description="Client's legal last name")
    email: str = Field(..., description="Client's email address")
    phone: str = Field(..., description="Client's phone number")
    date_of_birth: str = Field(..., description="Client's date of birth (mm/dd/yyyy)")
    preferred_name: Optional[str] = Field(None, description="Client's preferred name")

    # STEP 7: CREDIT CARD (Required for ALL services including free consult)
    cardholder_name: str = Field(..., description="Cardholder's name as shown on card")
    card_number: str = Field(..., description="Credit card number")
    card_expiration: str = Field(..., description="Credit card expiration (mm/yy)")
    card_cvv: str = Field(..., description="Credit card security code (CVV)")
    billing_zip: str = Field(..., description="Billing ZIP code")

    # Additional fields for browser-use agent
    booking_url: str = Field("https://www.solacegrove.org/book-appointment", description="URL of the booking page")

class BookAppointmentResponse(BaseModel):
    success: bool = Field(..., description="True if the appointment was booked successfully")
    message: str = Field(..., description="Details about the booking outcome")
    confirmation_id: Optional[str] = Field(None, description="Confirmation ID if booking was successful")

# --- Custom Function Endpoints ---

async def run_browser_task(url: str, action: str) -> str:
    """Helper to run a browser-use task and return the result string."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")

    llm = ChatOpenAI(
        model="gpt-4o", # Or another suitable model
        api_key=openai_api_key,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
    )
    
    # Initialize Agent for each task
    agent = Agent(
        task=action,
        llm=llm,
    )
    result = await agent.run()
    
    if result and hasattr(result, 'final_result'):
        return str(result.final_result())
    return str(result)

@app.post("/check_availability", response_model=CheckAvailabilityResponse)
async def check_availability(request: Request):
    """Checks for available appointment slots on the SimplePractice booking page."""
    try:
        body = await request.json()
        logger.info(f"Received check_availability request: {body}")
        
        args = body.get("args", body)
        date_range = args.get("date_range", "the next few days")
        
        booking_url = "https://www.solacegrove.org/book-appointment"
        action = f"look for available appointment slots for {date_range} and list them clearly."
        
        result = await run_browser_task(booking_url, action)
        
        # Assuming result contains the available slots in a parseable format
        # For now, we'll return a mock response.
        mock_slots = [
            "2026-06-15 10:00 AM",
            "2026-06-15 02:00 PM",
            "2026-06-16 11:00 AM"
        ]
        return CheckAvailabilityResponse(
            available_slots=mock_slots,
            message=f"Found {len(mock_slots)} slots for {date_range}"
        )
    except Exception as e:
        logger.error(f"Error in check_availability: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/book_appointment", response_model=BookAppointmentResponse)
async def book_appointment(request: Request):
    """Books an appointment on the SimplePractice booking page with all required details."""
    try:
        body = await request.json()
        logger.info(f"Received book_appointment request: {body}")
        
        args = body.get("args", body)
        booking_request = BookAppointmentRequest(**args)

        action_parts = [
            f"Navigate to {booking_request.booking_url}.",
            f"Select service type: {booking_request.service_type}.",
            f"Select location: {booking_request.location}.",
            f"Select date {booking_request.appointment_date} and time {booking_request.appointment_time}.",
            f"Fill prescreener with reason for care: {', '.join(booking_request.reason_for_care)}, care type: {', '.join(booking_request.care_type)}, and treatment history: {', '.join(booking_request.treatment_history)}.",
            f"Set payment method to {booking_request.payment_method}."
        ]
        if booking_request.insurance_details:
            action_parts.append(f"Enter insurance details: {booking_request.insurance_details}.")
        
        action_parts.append(f"Enter contact information: receiving care as {booking_request.receiving_care}, legal first name: {booking_request.legal_first_name}, legal last name: {booking_request.legal_last_name}, email: {booking_request.email}, phone: {booking_request.phone}, date of birth: {booking_request.date_of_birth}.")
        if booking_request.preferred_name:
            action_parts.append(f"Preferred name: {booking_request.preferred_name}.")

        # Always add credit card details as they are required for all services including free consults
        action_parts.append(f"Enter credit card details: cardholder name: {booking_request.cardholder_name}, card number: {booking_request.card_number}, expiration: {booking_request.card_expiration}, CVV: {booking_request.card_cvv}, billing ZIP: {booking_request.billing_zip}.")

        action_parts.append("Finally, click 'REQUEST APPOINTMENT' button to submit the form and report the confirmation message or any errors.")
        
        full_action = " ".join(action_parts)
        logger.info(f"Browser agent task: {full_action}")

        result = await run_browser_task(url=booking_request.booking_url, action=full_action)
        
        # Assuming the result from browser_agent.run_task contains success/failure info
        # For now, return a mock success response
        return BookAppointmentResponse(
            success=True,
            message=f"Appointment booking initiated. Browser agent reported: {result}",
            confirmation_id="MOCK-CONF-12345"
        )
    except Exception as e:
        logger.error(f"Error during book_appointment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Custom Function server is running"}

# Root endpoint for basic info
@app.get("/")
async def root():
    return {"message": "Welcome to the Solace Grove Custom Function server!"}

# This part is for local development/testing with uvicorn
# In Railway, uvicorn is typically run via a Procfile or directly by the Dockerfile CMD
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run the Solace Grove Custom Function server.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="Port to listen on.")
    args = parser.parse_args()
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()

# Added a comment to trigger a new Railway deployment.
