import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal

from strands import tool

logger = logging.getLogger(__name__)

# Demo only: in-memory, single-user. Production would use a database.
_encounters = {}
_patients = {
    "P-1001": {"first_name": "John", "last_name": "Smith", "dob": "1985-03-15", "phone": "+14155551234", "insurance": "BlueCross PPO"},
    "P-1002": {"first_name": "Maria", "last_name": "Garcia", "dob": "1992-07-22", "phone": "+14155555678", "insurance": "Aetna HMO"},
    "P-1003": {"first_name": "James", "last_name": "Wilson", "dob": "1978-11-30", "phone": "+14155559012", "insurance": "Medicare Part B"},
}


@tool
def create_encounter(
    caller_phone: str,
    call_start_time: str,
    channel: str = "inbound_call",
) -> dict:
    """Create a new encounter record at the start of a patient call.
    Call this IMMEDIATELY when a caller is connected, before collecting
    any other information. Returns encounter_id that must be used in all
    subsequent tool calls.

    Args:
        caller_phone: Caller's phone number in E.164 format (e.g., +14155551234)
        call_start_time: ISO 8601 timestamp when call was answered
        channel: How the call originated - inbound_call or callback

    Returns:
        dict with encounter_id, created_at, status
    """
    encounter_id = f"ENC-{uuid.uuid4().hex[:8].upper()}"
    encounter = {
        "encounter_id": encounter_id,
        "caller_phone": caller_phone,
        "call_start_time": call_start_time,
        "channel": channel,
        "status": "in_progress",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "patient_id": None,
        "chief_complaint": None,
        "symptoms": [],
        "triage_result": None,
    }
    _encounters[encounter_id] = encounter
    logger.info("Created encounter %s for %s", encounter_id, caller_phone)
    return {
        "encounter_id": encounter_id,
        "created_at": encounter["created_at"],
        "status": "in_progress",
    }


@tool
def match_patient(
    encounter_id: str,
    first_name: str,
    last_name: str,
    date_of_birth: Optional[str] = None,
    phone: Optional[str] = None,
    last_4_ssn: Optional[str] = None,
) -> dict:
    """Match the caller to an existing patient record. Use phone + name first;
    if multiple matches, ask caller for DOB to disambiguate. Do NOT call this
    until you have at least first name, last name, and one of (DOB, phone,
    last_4_ssn).

    Returns match_confidence (high/medium/low/none) and patient_id if matched.
    If match_confidence is 'low' or 'none', treat as new patient and ask for
    additional demographics.

    Args:
        encounter_id: From create_encounter
        first_name: Patient's first name as spoken
        last_name: Patient's last name as spoken
        date_of_birth: YYYY-MM-DD if provided
        phone: E.164 format
        last_4_ssn: Last 4 digits of SSN, only if patient volunteers

    Returns:
        dict with patient_id, match_confidence, patient_summary
    """
    first_lower = first_name.lower()
    last_lower = last_name.lower()

    matches = []
    for pid, p in _patients.items():
        score = 0
        if p["first_name"].lower() == first_lower and p["last_name"].lower() == last_lower:
            score += 2
        if phone and p.get("phone") == phone:
            score += 2
        if date_of_birth and p.get("dob") == date_of_birth:
            score += 3
        if score > 0:
            matches.append((pid, p, score))

    matches.sort(key=lambda x: x[2], reverse=True)

    if matches and matches[0][2] >= 4:
        pid, p, _ = matches[0]
        if encounter_id in _encounters:
            _encounters[encounter_id]["patient_id"] = pid
        return {
            "patient_id": pid,
            "match_confidence": "high",
            "patient_summary": f"{p['first_name']} {p['last_name']}, DOB {p['dob']}, {p.get('insurance', 'N/A')}",
        }
    elif matches and matches[0][2] >= 2:
        pid, p, _ = matches[0]
        return {
            "patient_id": pid,
            "match_confidence": "medium",
            "patient_summary": f"Possible match: {p['first_name']} {p['last_name']}, DOB {p['dob']}. Please confirm date of birth to verify.",
        }
    else:
        return {
            "patient_id": None,
            "match_confidence": "none",
            "patient_summary": "No matching patient found. Please collect full demographics to register as new patient.",
        }


@tool
def update_encounter(
    encounter_id: str,
    patient_id: Optional[str] = None,
    chief_complaint: Optional[str] = None,
    symptoms: Optional[str] = None,
    symptom_onset: Optional[str] = None,
    pain_level: Optional[int] = None,
    notes: Optional[str] = None,
) -> dict:
    """Update the encounter record with information gathered during the call.
    Call this incrementally as you learn new information, not just at the end.
    pain_level is 0-10 scale.

    Args:
        encounter_id: From create_encounter
        patient_id: From match_patient if available
        chief_complaint: Primary reason for call in patient's words
        symptoms: Comma-separated list of symptoms mentioned
        symptom_onset: When symptoms started (free text like '2 hours ago')
        pain_level: Integer 0-10 if patient reports pain
        notes: Free-form notes from conversation

    Returns:
        dict with updated encounter state
    """
    enc = _encounters.get(encounter_id)
    if not enc:
        return {"error": f"Encounter {encounter_id} not found"}

    if patient_id:
        enc["patient_id"] = patient_id
    if chief_complaint:
        enc["chief_complaint"] = chief_complaint
    if symptoms:
        symptom_list = [s.strip() for s in symptoms.split(",")]
        enc["symptoms"] = list(set(enc.get("symptoms", []) + symptom_list))
    if symptom_onset:
        enc["symptom_onset"] = symptom_onset
    if pain_level is not None:
        enc["pain_level"] = pain_level
    if notes:
        enc.setdefault("notes", []).append(notes)

    logger.info("Updated encounter %s: complaint=%s, symptoms=%s", encounter_id, enc.get("chief_complaint"), enc.get("symptoms"))
    return {
        "encounter_id": encounter_id,
        "status": enc["status"],
        "chief_complaint": enc.get("chief_complaint"),
        "symptoms": enc.get("symptoms", []),
        "pain_level": enc.get("pain_level"),
        "patient_id": enc.get("patient_id"),
    }


@tool
def triage_symptoms(
    encounter_id: str,
    chief_complaint: str,
    symptoms: str,
    patient_age: Optional[int] = None,
    patient_sex: Optional[str] = None,
) -> dict:
    """Run clinical triage protocol (Schmitt-Thompson-based) against reported
    symptoms. Returns acuity level and recommended disposition.

    Only call this AFTER you have chief_complaint and at least 2 symptoms
    logged via update_encounter.

    Acuity levels:
    - 'emergency': Instruct to call 911 immediately
    - 'urgent': Transfer to nurse immediately
    - 'routine': Schedule callback or self-care instructions
    - 'info_only': Provide information, no medical intervention needed

    Args:
        encounter_id: From create_encounter
        chief_complaint: Primary complaint
        symptoms: Comma-separated list of all symptoms gathered
        patient_age: Age in years if known
        patient_sex: M, F, or other if known

    Returns:
        dict with acuity, disposition, protocol_matched, reasoning
    """
    symptom_list = [s.strip().lower() for s in symptoms.split(",")]

    emergency_indicators = ["chest pain", "difficulty breathing", "severe bleeding", "unconscious", "stroke symptoms", "allergic reaction"]
    urgent_indicators = ["high fever", "persistent vomiting", "severe headache", "abdominal pain", "dehydration"]

    if any(ind in " ".join(symptom_list) for ind in emergency_indicators):
        acuity = "emergency"
        disposition = "Instruct caller to hang up and call 911 immediately"
        protocol = "Schmitt-Thompson: Life-Threatening Symptoms"
        reasoning = f"Emergency indicators detected in symptoms: {', '.join(symptom_list)}"
    elif any(ind in " ".join(symptom_list) for ind in urgent_indicators):
        acuity = "urgent"
        disposition = "Transfer to triage nurse for immediate assessment"
        protocol = "Schmitt-Thompson: Urgent Care Required"
        reasoning = f"Urgent indicators present. Chief complaint: {chief_complaint}"
    elif len(symptom_list) >= 3:
        acuity = "routine"
        disposition = "Schedule nurse callback within 1 hour"
        protocol = "Schmitt-Thompson: Routine Assessment"
        reasoning = f"Multiple non-urgent symptoms reported for: {chief_complaint}"
    else:
        acuity = "info_only"
        disposition = "Provide self-care guidance"
        protocol = "Schmitt-Thompson: Information/Self-Care"
        reasoning = f"Minor symptoms for: {chief_complaint}"

    if encounter_id in _encounters:
        _encounters[encounter_id]["triage_result"] = {"acuity": acuity, "disposition": disposition}

    logger.info("Triage for %s: acuity=%s", encounter_id, acuity)
    return {
        "acuity": acuity,
        "disposition": disposition,
        "protocol_matched": protocol,
        "reasoning": reasoning,
    }


@tool
def find_hospital_location(
    encounter_id: str,
    patient_zip_code: Optional[str] = None,
    patient_address: Optional[str] = None,
    facility_type: str = "ed",
    specialty: Optional[str] = None,
) -> dict:
    """Find nearest appropriate facility based on patient location and needed
    care type. Use facility_type='ed' for emergency triage results,
    'urgent_care' for urgent but non-emergency, 'clinic' for routine.

    Args:
        encounter_id: From create_encounter
        patient_zip_code: 5-digit US ZIP
        patient_address: Full address if ZIP not available
        facility_type: ed, urgent_care, clinic, or pharmacy
        specialty: Optional specialty filter (e.g., pediatric, cardiac)

    Returns:
        dict with list of facilities: name, address, distance_miles, phone, wait_time_estimate, in_network
    """
    facilities_db = {
        "ed": [
            {"name": "St. Mary's Medical Center - Emergency", "address": "450 Stanyan St, San Francisco, CA 94117", "distance_miles": 2.1, "phone": "+14157506000", "wait_time_estimate": "25 min", "in_network": True},
            {"name": "UCSF Medical Center - Emergency", "address": "505 Parnassus Ave, San Francisco, CA 94143", "distance_miles": 3.4, "phone": "+14154762000", "wait_time_estimate": "40 min", "in_network": True},
        ],
        "urgent_care": [
            {"name": "Carbon Health Urgent Care", "address": "2101 Mission St, San Francisco, CA 94110", "distance_miles": 1.8, "phone": "+14155551000", "wait_time_estimate": "15 min", "in_network": True},
            {"name": "One Medical - Urgent Care", "address": "1 Embarcadero Center, San Francisco, CA 94111", "distance_miles": 4.2, "phone": "+14155552000", "wait_time_estimate": "10 min", "in_network": False},
        ],
        "clinic": [
            {"name": "AnyHealth Partner Clinic - Mission", "address": "2400 Mission St, San Francisco, CA 94110", "distance_miles": 1.5, "phone": "+14155553000", "wait_time_estimate": "By appointment", "in_network": True},
        ],
        "pharmacy": [
            {"name": "Walgreens Pharmacy", "address": "3201 Divisadero St, San Francisco, CA 94123", "distance_miles": 0.8, "phone": "+14155554000", "wait_time_estimate": "No wait", "in_network": True},
        ],
    }

    results = facilities_db.get(facility_type, facilities_db["ed"])
    logger.info("Facility search for %s: type=%s, found %d", encounter_id, facility_type, len(results))
    return {"facilities": results, "search_criteria": {"zip": patient_zip_code, "type": facility_type, "specialty": specialty}}


@tool
def escalate_to_nurse(
    encounter_id: str,
    urgency: str,
    handoff_summary: str,
    preferred_callback_number: Optional[str] = None,
) -> dict:
    """Escalate the call to a human nurse. Use 'immediate' for urgent triage
    results (live transfer), 'callback_15min' for high-priority but stable,
    'callback_1hr' for routine follow-up.

    handoff_summary must be a concise clinical summary the nurse can read
    in under 15 seconds. Include: patient identifier, chief complaint, key
    symptoms, triage level, any red flags.

    Args:
        encounter_id: From create_encounter
        urgency: immediate, callback_15min, or callback_1hr
        handoff_summary: Structured summary for receiving nurse
        preferred_callback_number: If different from caller_phone

    Returns:
        dict with escalation_id, estimated_callback_time, queue_position
    """
    escalation_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"

    callback_times = {
        "immediate": "Transferring now",
        "callback_15min": "Within 15 minutes",
        "callback_1hr": "Within 1 hour",
    }
    queue_positions = {
        "immediate": 1,
        "callback_15min": 3,
        "callback_1hr": 8,
    }

    if encounter_id in _encounters:
        _encounters[encounter_id]["status"] = "escalated"
        _encounters[encounter_id]["escalation_id"] = escalation_id

    logger.info("Escalation %s for %s: urgency=%s", escalation_id, encounter_id, urgency)
    return {
        "escalation_id": escalation_id,
        "urgency": urgency,
        "estimated_callback_time": callback_times.get(urgency, "Unknown"),
        "queue_position": queue_positions.get(urgency, 10),
        "handoff_summary_received": True,
        "callback_number": preferred_callback_number or (_encounters.get(encounter_id, {}).get("caller_phone", "on file")),
    }


CLINICAL_TOOLS = [
    create_encounter,
    match_patient,
    update_encounter,
    triage_symptoms,
    find_hospital_location,
    escalate_to_nurse,
]

CLINICAL_SYSTEM_PROMPT = """You are AnyHealth's clinical reasoning agent invoked by a voice front-end during patient intake calls. You never speak directly to the patient — you execute the right sequence of tools and return a concise result the voice agent can speak back.

Workflow rules:
1. Every call starts with create_encounter — if encounter_id is not in context, call it first.
2. Call match_patient as soon as you have name + one identifier.
3. Incrementally update_encounter as information comes in.
4. Only call triage_symptoms when chief_complaint + at least 2 symptoms are set.
5. After triage, if acuity is emergency/urgent, call escalate_to_nurse with urgency='immediate' BEFORE find_hospital_location.
6. Return a clear, speakable summary in under 30 words for the voice layer."""
