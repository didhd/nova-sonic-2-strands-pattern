import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from strands import tool

logger = logging.getLogger(__name__)

# Demo only: in-memory, single-user. Production would use a database.
_encounters = {}
_patients = {
    "P-1001": {"first_name": "John", "last_name": "Smith", "dob": "1985-03-15", "phone": "+14155551234", "insurance": "BlueCross PPO", "allergies": ["penicillin"], "conditions": ["hypertension"]},
    "P-1002": {"first_name": "Maria", "last_name": "Garcia", "dob": "1992-07-22", "phone": "+14155555678", "insurance": "Aetna HMO", "allergies": [], "conditions": []},
    "P-1003": {"first_name": "James", "last_name": "Wilson", "dob": "1978-11-30", "phone": "+14155559012", "insurance": "Medicare Part B", "allergies": ["sulfa"], "conditions": ["diabetes type 2"]},
}


@tool
def register_patient(
    first_name: str,
    last_name: str,
    phone: str,
    date_of_birth: str,
    chief_complaint: str,
    insurance: Optional[str] = None,
) -> dict:
    """Register a patient and create an encounter in one step. Call this once you
    have collected the patient's name, phone, date of birth, and reason for calling.

    This will:
    1. Create a new encounter record
    2. Attempt to match the patient against existing records
    3. Store the chief complaint

    Args:
        first_name: Patient's first name
        last_name: Patient's last name
        phone: Phone number (any format, will be normalized)
        date_of_birth: Date of birth (YYYY-MM-DD)
        chief_complaint: Why the patient is calling, in their own words
        insurance: Insurance provider name if mentioned

    Returns:
        dict with encounter_id, patient match result, and next steps
    """
    normalized_phone = "+" + "".join(c for c in phone if c.isdigit())
    if not normalized_phone.startswith("+1") and len(normalized_phone) == 11:
        normalized_phone = "+1" + normalized_phone[1:]

    encounter_id = f"ENC-{uuid.uuid4().hex[:8].upper()}"
    encounter = {
        "encounter_id": encounter_id,
        "caller_phone": normalized_phone,
        "call_start_time": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
        "patient_id": None,
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": date_of_birth,
        "chief_complaint": chief_complaint,
        "symptoms": [],
        "triage_result": None,
    }
    _encounters[encounter_id] = encounter

    patient_match = None
    for pid, p in _patients.items():
        if (p["first_name"].lower() == first_name.lower()
            and p["last_name"].lower() == last_name.lower()
            and p.get("dob") == date_of_birth):
            encounter["patient_id"] = pid
            patient_match = {
                "patient_id": pid,
                "status": "existing_patient",
                "insurance": p.get("insurance", "unknown"),
                "allergies": p.get("allergies", []),
                "conditions": p.get("conditions", []),
            }
            break

    if not patient_match:
        for pid, p in _patients.items():
            if p.get("phone") == normalized_phone:
                encounter["patient_id"] = pid
                patient_match = {
                    "patient_id": pid,
                    "status": "matched_by_phone",
                    "insurance": p.get("insurance", "unknown"),
                    "allergies": p.get("allergies", []),
                    "conditions": p.get("conditions", []),
                }
                break

    if not patient_match:
        patient_match = {"patient_id": None, "status": "new_patient"}

    logger.info("Registered %s %s, encounter=%s, match=%s", first_name, last_name, encounter_id, patient_match["status"])
    return {
        "encounter_id": encounter_id,
        "patient": patient_match,
        "chief_complaint": chief_complaint,
        "next_step": "Ask about symptoms: when did it start, severity (1-10), and any other symptoms.",
    }


@tool
def record_symptoms(
    encounter_id: str,
    symptoms: str,
    onset: Optional[str] = None,
    severity: Optional[int] = None,
    medications_tried: Optional[str] = None,
) -> dict:
    """Record the patient's symptoms and run triage assessment.

    Args:
        encounter_id: From register_patient
        symptoms: Comma-separated list of symptoms (e.g., 'headache, nausea, dizziness')
        onset: When symptoms started (e.g., '2 hours ago', 'yesterday morning')
        severity: Pain/discomfort level 1-10
        medications_tried: Any medications already taken (e.g., 'took ibuprofen 2 hours ago')

    Returns:
        dict with triage result and recommended action
    """
    enc = _encounters.get(encounter_id)
    if not enc:
        return {"error": f"Encounter {encounter_id} not found"}

    symptom_list = [s.strip().lower() for s in symptoms.split(",")]
    enc["symptoms"] = symptom_list
    if onset:
        enc["symptom_onset"] = onset
    if severity is not None:
        enc["severity"] = severity
    if medications_tried:
        enc["medications_tried"] = medications_tried

    emergency_keywords = ["chest pain", "difficulty breathing", "severe bleeding",
                          "unconscious", "stroke", "seizure", "allergic reaction",
                          "suicidal", "overdose"]
    urgent_keywords = ["high fever", "fever over 103", "persistent vomiting",
                       "severe headache", "abdominal pain", "dehydration",
                       "broken bone", "deep cut"]

    combined = " ".join(symptom_list) + " " + (enc.get("chief_complaint") or "")

    if any(kw in combined for kw in emergency_keywords):
        acuity = "emergency"
        action = "Tell the patient to call 911 or go to the nearest emergency room immediately."
    elif any(kw in combined for kw in urgent_keywords) or (severity and severity >= 8):
        acuity = "urgent"
        action = "Transfer to a triage nurse now for immediate assessment."
    elif severity and severity >= 5 or len(symptom_list) >= 3:
        acuity = "semi-urgent"
        action = "A nurse will call back within 30 minutes."
    else:
        acuity = "routine"
        action = "Provide self-care advice or schedule a nurse callback within 2 hours."

    enc["triage_result"] = {"acuity": acuity, "action": action}
    logger.info("Triage %s: acuity=%s, symptoms=%s", encounter_id, acuity, symptom_list)

    return {
        "encounter_id": encounter_id,
        "acuity": acuity,
        "action": action,
        "symptoms_recorded": symptom_list,
        "severity": severity,
    }


@tool
def find_nearby_facility(
    zip_code: Optional[str] = None,
    city: Optional[str] = None,
    facility_type: str = "urgent_care",
) -> dict:
    """Find the nearest healthcare facility. Use after triage if the patient
    needs to visit a facility.

    Args:
        zip_code: Patient's ZIP code if known
        city: City name if ZIP not available
        facility_type: One of: emergency, urgent_care, clinic, pharmacy

    Returns:
        dict with nearest facilities
    """
    facilities = {
        "emergency": [
            {"name": "St. Mary's Medical Center ER", "address": "450 Stanyan St, San Francisco, CA", "phone": "(415) 750-6000", "wait": "~25 min"},
            {"name": "UCSF Emergency Department", "address": "505 Parnassus Ave, San Francisco, CA", "phone": "(415) 476-2000", "wait": "~40 min"},
        ],
        "urgent_care": [
            {"name": "Carbon Health Urgent Care", "address": "2101 Mission St, San Francisco, CA", "phone": "(415) 355-1000", "wait": "~15 min"},
            {"name": "One Medical Urgent Care", "address": "1 Embarcadero Center, San Francisco, CA", "phone": "(415) 355-2000", "wait": "~10 min"},
        ],
        "clinic": [
            {"name": "AnyHealth Partner Clinic", "address": "2400 Mission St, San Francisco, CA", "phone": "(415) 355-3000", "wait": "By appointment"},
        ],
        "pharmacy": [
            {"name": "Walgreens", "address": "3201 Divisadero St, San Francisco, CA", "phone": "(415) 355-4000", "wait": "No wait"},
        ],
    }
    results = facilities.get(facility_type, facilities["urgent_care"])
    return {"facilities": results[:2], "facility_type": facility_type}


@tool
def transfer_to_nurse(
    encounter_id: str,
    priority: str,
    summary: str,
) -> dict:
    """Transfer the call to a registered nurse. Use this after triage indicates
    the patient needs to speak with a nurse.

    Args:
        encounter_id: From register_patient
        priority: One of: immediate (live transfer), callback_30min, callback_2hr
        summary: Brief clinical summary for the nurse (who, what, severity)

    Returns:
        dict with transfer status and estimated wait time
    """
    enc = _encounters.get(encounter_id)
    if enc:
        enc["status"] = "transferred"

    transfer_id = f"TRN-{uuid.uuid4().hex[:6].upper()}"
    wait_times = {
        "immediate": "Connecting now — please hold",
        "callback_30min": "A nurse will call you back within 30 minutes",
        "callback_2hr": "A nurse will call you back within 2 hours",
    }

    logger.info("Transfer %s: priority=%s, encounter=%s", transfer_id, priority, encounter_id)
    return {
        "transfer_id": transfer_id,
        "priority": priority,
        "message": wait_times.get(priority, "A nurse will be in touch soon"),
        "summary_received": True,
    }


CLINICAL_TOOLS = [
    register_patient,
    record_symptoms,
    find_nearby_facility,
    transfer_to_nurse,
]

CLINICAL_SYSTEM_PROMPT = """You are a clinical intake agent behind a voice assistant. You receive patient information collected by the voice front-end and execute the appropriate tools. You never speak to the patient.

Typical call flow:
1. register_patient — when you receive name, phone, DOB, and reason for calling
2. record_symptoms — when you receive symptom details (what, when, severity)
3. Based on triage result:
   - emergency → tell the voice assistant to instruct 911
   - urgent/semi-urgent → transfer_to_nurse
   - routine → provide self-care advice via the voice assistant
4. find_nearby_facility — if the patient needs to visit somewhere

Rules:
- Always call at least one tool per request.
- If a field is missing, return {"missing": ["field_name"]} so the voice assistant can ask.
- Return only a short speakable summary (under 30 words) after tool execution.
- No markdown, no bullet points, no explanations."""
