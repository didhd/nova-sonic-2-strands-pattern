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
def create_encounter(
    caller_phone: str,
    channel: str = "inbound_call",
) -> dict:
    """Start a new call encounter. Call this as soon as the patient provides their phone number.

    Args:
        caller_phone: Patient's phone number in any format
        channel: How the call originated - inbound_call or callback

    Returns:
        dict with encounter_id and status
    """
    normalized = "+" + "".join(c for c in caller_phone if c.isdigit())
    encounter_id = f"ENC-{uuid.uuid4().hex[:8].upper()}"
    _encounters[encounter_id] = {
        "encounter_id": encounter_id,
        "caller_phone": normalized,
        "call_start_time": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "status": "in_progress",
        "patient_id": None,
        "chief_complaint": None,
        "symptoms": [],
        "triage_result": None,
    }
    logger.info("Created encounter %s for %s", encounter_id, normalized)
    return {"encounter_id": encounter_id, "status": "in_progress"}


@tool
def match_patient(
    encounter_id: str,
    first_name: str,
    last_name: str,
    date_of_birth: str,
    phone: Optional[str] = None,
) -> dict:
    """Look up the patient in the system. Call this once you have name and date of birth.

    Args:
        encounter_id: From create_encounter
        first_name: Patient's first name
        last_name: Patient's last name
        date_of_birth: YYYY-MM-DD format
        phone: Phone number if available

    Returns:
        dict with patient match result, allergies, and existing conditions
    """
    for pid, p in _patients.items():
        if (p["first_name"].lower() == first_name.lower()
                and p["last_name"].lower() == last_name.lower()
                and p.get("dob") == date_of_birth):
            if encounter_id in _encounters:
                _encounters[encounter_id]["patient_id"] = pid
            return {
                "patient_id": pid,
                "status": "found",
                "name": f"{p['first_name']} {p['last_name']}",
                "insurance": p.get("insurance", "none"),
                "allergies": p.get("allergies", []),
                "conditions": p.get("conditions", []),
            }

    if phone:
        normalized = "+" + "".join(c for c in phone if c.isdigit())
        for pid, p in _patients.items():
            if p.get("phone") == normalized:
                if encounter_id in _encounters:
                    _encounters[encounter_id]["patient_id"] = pid
                return {
                    "patient_id": pid,
                    "status": "found_by_phone",
                    "name": f"{p['first_name']} {p['last_name']}",
                    "insurance": p.get("insurance", "none"),
                    "allergies": p.get("allergies", []),
                    "conditions": p.get("conditions", []),
                }

    return {"patient_id": None, "status": "new_patient", "message": "No existing record found. Patient will be registered as new."}


@tool
def update_encounter(
    encounter_id: str,
    chief_complaint: Optional[str] = None,
    symptoms: Optional[str] = None,
    symptom_onset: Optional[str] = None,
    severity: Optional[int] = None,
    medications_tried: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Update the encounter with new information. Call this whenever the patient shares
    new details — chief complaint, symptoms, severity, etc.

    Args:
        encounter_id: From create_encounter
        chief_complaint: Why the patient is calling, in their words
        symptoms: Comma-separated symptoms (e.g., 'headache, nausea')
        symptom_onset: When symptoms started (e.g., 'yesterday', '2 hours ago')
        severity: Pain or discomfort level 1-10
        medications_tried: Any medications already taken
        notes: Any other relevant notes

    Returns:
        dict with updated encounter summary
    """
    enc = _encounters.get(encounter_id)
    if not enc:
        return {"error": f"Encounter {encounter_id} not found"}

    if chief_complaint:
        enc["chief_complaint"] = chief_complaint
    if symptoms:
        enc["symptoms"] = list(set(enc.get("symptoms", []) + [s.strip() for s in symptoms.split(",")]))
    if symptom_onset:
        enc["symptom_onset"] = symptom_onset
    if severity is not None:
        enc["severity"] = severity
    if medications_tried:
        enc["medications_tried"] = medications_tried
    if notes:
        enc.setdefault("notes", []).append(notes)

    logger.info("Updated %s: complaint=%s symptoms=%s severity=%s", encounter_id, enc.get("chief_complaint"), enc.get("symptoms"), enc.get("severity"))
    return {
        "encounter_id": encounter_id,
        "chief_complaint": enc.get("chief_complaint"),
        "symptoms": enc.get("symptoms", []),
        "severity": enc.get("severity"),
    }


@tool
def triage_symptoms(
    encounter_id: str,
) -> dict:
    """Run triage assessment on the encounter. Call this after symptoms and severity
    have been recorded via update_encounter.

    Args:
        encounter_id: From create_encounter

    Returns:
        dict with acuity level and recommended action
    """
    enc = _encounters.get(encounter_id)
    if not enc:
        return {"error": f"Encounter {encounter_id} not found"}

    symptoms = enc.get("symptoms", [])
    severity = enc.get("severity")
    complaint = enc.get("chief_complaint", "")
    combined = " ".join(symptoms).lower() + " " + complaint.lower()

    emergency = ["chest pain", "difficulty breathing", "severe bleeding", "unconscious", "stroke", "seizure", "allergic reaction", "suicidal", "overdose"]
    urgent = ["high fever", "fever over 103", "persistent vomiting", "severe headache", "abdominal pain", "broken bone", "deep cut"]

    if any(kw in combined for kw in emergency):
        acuity, action = "emergency", "Patient must call 911 or go to the ER immediately."
    elif any(kw in combined for kw in urgent) or (severity and severity >= 8):
        acuity, action = "urgent", "Transfer to a triage nurse now."
    elif (severity and severity >= 5) or len(symptoms) >= 3:
        acuity, action = "semi-urgent", "A nurse will call back within 30 minutes."
    else:
        acuity, action = "routine", "Self-care advice is appropriate. A nurse can call back within 2 hours if needed."

    enc["triage_result"] = {"acuity": acuity, "action": action}
    logger.info("Triage %s: acuity=%s", encounter_id, acuity)
    return {"acuity": acuity, "action": action, "encounter_id": encounter_id}


@tool
def find_nearby_facility(
    zip_code: Optional[str] = None,
    city: Optional[str] = None,
    facility_type: str = "urgent_care",
) -> dict:
    """Find the nearest healthcare facility. Call this if the patient needs
    to visit a facility based on triage results.

    Args:
        zip_code: Patient's ZIP code
        city: City name if ZIP not known
        facility_type: One of: emergency, urgent_care, clinic, pharmacy

    Returns:
        dict with nearest facilities and contact info
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
    return {"facilities": facilities.get(facility_type, facilities["urgent_care"])[:2], "facility_type": facility_type}


@tool
def transfer_to_nurse(
    encounter_id: str,
    priority: str,
    summary: str,
) -> dict:
    """Transfer the call to a registered nurse. Call this when triage indicates
    the patient needs to speak with a nurse.

    Args:
        encounter_id: From create_encounter
        priority: One of: immediate, callback_30min, callback_2hr
        summary: Brief summary for the nurse — who, what, how severe

    Returns:
        dict with transfer status and estimated wait
    """
    enc = _encounters.get(encounter_id)
    if enc:
        enc["status"] = "transferred"

    transfer_id = f"TRN-{uuid.uuid4().hex[:6].upper()}"
    wait = {"immediate": "Connecting now, please hold", "callback_30min": "A nurse will call back within 30 minutes", "callback_2hr": "A nurse will call back within 2 hours"}

    logger.info("Transfer %s: priority=%s encounter=%s", transfer_id, priority, encounter_id)
    return {"transfer_id": transfer_id, "priority": priority, "message": wait.get(priority, "A nurse will be in touch")}


CLINICAL_TOOLS = [
    create_encounter,
    match_patient,
    update_encounter,
    triage_symptoms,
    find_nearby_facility,
    transfer_to_nurse,
]

CLINICAL_SYSTEM_PROMPT = """You are a clinical intake agent behind a voice assistant. Execute exactly ONE tool per request.

Which tool to call:
- Patient gave phone number → create_encounter
- Patient gave name + DOB → match_patient (needs encounter_id)
- Patient described complaint, symptoms, severity, or onset → update_encounter (needs encounter_id)
- Symptoms and severity recorded, ready for assessment → triage_symptoms (needs encounter_id)
- Patient needs to find a facility → find_nearby_facility
- Triage says urgent/emergency, needs a nurse → transfer_to_nurse (needs encounter_id)

If required fields are missing, return {"missing": ["field_name"]}.
After calling the tool, return ONLY a speakable summary under 30 words. No markdown."""
