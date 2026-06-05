from pydantic import BaseModel
from typing import Optional

class LoginRequest(BaseModel):
    username: str
    password: str

class PatientCreate(BaseModel):
    name: str
    age: int
    gender: str
    room_no: str
    diagnosis: str
    assigned_nurse: Optional[str] = None
    caretaker: Optional[str] = None

class CareLogCreate(BaseModel):
    patient_id: str
    created_by: str
    role: str
    meal_type: Optional[str] = None
    fluid_intake_ml: Optional[float] = None
    food_intake: Optional[str] = None
    blood_pressure: Optional[str] = None
    oxygen_level: Optional[float] = None
    sugar_level: Optional[str] = None
    sleep_hours: Optional[float] = None
    confusion: Optional[bool] = None
    notes: Optional[str] = None
    # Dynamic extra fields from log_fields registry
    extra_fields: Optional[dict] = None

class TaskCreate(BaseModel):
    patient_id: str
    assigned_to: Optional[str] = None
    created_by: str
    title: str
    due_time: str
    instruction: Optional[str] = None
    linked_field: Optional[str] = None   # field key from log_fields e.g. "blood_pressure"
                                          # blank or unrecognised → manual completion

class TaskCompleteRequest(BaseModel):
    task_id: str
    completed_by: str

class PolicyCreate(BaseModel):
    name: str
    policy_type: str              # 'threshold' or 'yes_no'
    log_field: str                # which care log field to check
    scope: str                    # 'organization' or 'patient'
    patient_id: Optional[str] = None
    description: Optional[str] = ""
    # Threshold type
    check_value: Optional[float] = None
    threshold: Optional[str] = ""
    direction: Optional[str] = "below"  # 'below' or 'above'
    # Both types
    alert_days: int = 3
    prealert_days: int = 2
    # Yes/No type
    tie_rule: Optional[str] = "breach"  # 'breach' or 'no_breach'
    # Evaluation mode
    evaluation_mode: Optional[str] = "instant"  # 'instant' or 'end_of_day_cumulative'
    cutoff_time: Optional[str] = None           # e.g. '20:00' only for cumulative

class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    check_value: Optional[float] = None
    threshold: Optional[str] = None
    alert_days: Optional[int] = None
    prealert_days: Optional[int] = None
    tie_rule: Optional[str] = None
    direction: Optional[str] = None
    description: Optional[str] = None
    evaluation_mode: Optional[str] = None
    cutoff_time: Optional[str] = None

class LogFieldCreate(BaseModel):
    field: str           # Python/DB field name e.g. 'appetite_loss'
    label: str           # Display label e.g. 'Appetite Loss'
    type: str            # 'threshold' or 'yes_no'
    unit: Optional[str] = None
    description: Optional[str] = ""
    extract: Optional[str] = None  # e.g. 'systolic' for blood_pressure

class RoomCreate(BaseModel):
    room_no: str

class TriggerPreAlert(BaseModel):
    pre_alert_id: str
    triggered_by: str

class UserCreate(BaseModel):
    name: str
    age: int
    password: str
    role: str

class AssignPatient(BaseModel):
    patient_id: str
    worker_username: str
    mode: str

class DeleteTaskRequest(BaseModel):
    task_id: str
    deleted_by: str

class PolicyRemoveRequest(BaseModel):
    patient_id: str
    policy_id: str
    requested_by: str

class PolicyDecision(BaseModel):
    request_id: str
    decision_by: str
    decision: str

class DocAction(BaseModel):
    doc_id: str

class PatientAction(BaseModel):
    patient_id: str

class WorkerDelete(BaseModel):
    username: str
    transfer_to: Optional[str] = None

class TaskAckRequest(BaseModel):
    notification_id: str
    username: str

class PolicyRequestCreate(BaseModel):
    patient_id: str
    requested_by: str
    name: str
    threshold: str
    description: str
    # Dynamic policy fields for doctor requests
    policy_type: Optional[str] = "none"
    log_field: Optional[str] = None
    check_value: Optional[float] = None
    alert_days: Optional[int] = 3
    prealert_days: Optional[int] = 2
    tie_rule: Optional[str] = "breach"
    direction: Optional[str] = "below"

class NotificationAckRequest(BaseModel):
    notification_id: str
    username: str

class NewPatientAssignRequest(BaseModel):
    patient_id: str
    worker_username: str
    mode: str = "nurse"

class IncidentCreate(BaseModel):
    patient_id: str
    patient_name: str
    reported_by: str
    summary: str
