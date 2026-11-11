import ipaddress
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import UUID4, BaseModel, BeforeValidator, Field


class ModalityCodeChoices(str, Enum):
    # DICOM modality codes (DCM coding scheme), as sent in Modality (0008,0060)
    AR = "AR"  # Autorefraction
    BMD = "BMD"  # Bone Mineral Densitometry
    BDUS = "BDUS"  # Ultrasound Bone Densitometry
    EPS = "EPS"  # Cardiac Electrophysiology
    CR = "CR"  # Computed Radiography
    CT = "CT"  # Computed Tomography
    DX = "DX"  # Digital Radiography
    ECG = "ECG"  # Electrocardiography
    ES = "ES"  # Endoscopy
    XC = "XC"  # External-camera Photography
    GM = "GM"  # General Microscopy
    HD = "HD"  # Hemodynamic Waveform
    IO = "IO"  # Intra-oral Radiography
    IVOCT = "IVOCT"  # Intravascular Optical Coherence Tomography
    IVUS = "IVUS"  # Intravascular Ultrasound
    KER = "KER"  # Keratometry
    LEN = "LEN"  # Lensometry
    MR = "MR"  # Magnetic Resonance
    MG = "MG"  # Mammography
    NM = "NM"  # Nuclear Medicine
    OAM = "OAM"  # Ophthalmic Axial Measurements
    OCT = "OCT"  # Optical Coherence Tomography
    OPM = "OPM"  # Ophthalmic Mapping
    OP = "OP"  # Ophthalmic Photography
    OPR = "OPR"  # Ophthalmic Refraction
    OPT = "OPT"  # Ophthalmic Tomography
    OPV = "OPV"  # Ophthalmic Visual Field
    OSS = "OSS"  # Optical Surface Scanner
    PX = "PX"  # Panoramic X-Ray
    PT = "PT"  # Positron emission tomography
    RF = "RF"  # Radiofluoroscopy
    RG = "RG"  # Radiographic imaging
    SM = "SM"  # Slide Microscopy
    SRF = "SRF"  # Subjective Refraction
    US = "US"  # Ultrasound
    VA = "VA"  # Visual Acuity
    XA = "XA"  # X-Ray Angiography


# DICOM AE value: leading and trailing spaces are not significant, and a value of only spaces is not allowed.
# Only printable ASCII is allowed, excluding the backslash.
AETitle = Annotated[
    str,
    BeforeValidator(lambda value: value.strip(" ") if isinstance(value, str) else value),
    Field(min_length=1, max_length=16, pattern=r"^[\x20-\x5B\x5D-\x7E]+$"),
]


class ModalityMachineSpec(BaseModel):
    ae_title: AETitle
    modality: ModalityCodeChoices
    ip: ipaddress.IPv4Address


class DicomEndpointSpec(BaseModel):
    ae_title: AETitle
    host: str | None = None
    port: int = Field(ge=1, le=65535)


AssignmentStatus = Literal["unassigned", "assigned"]


class DicomDeviceMetadataWriteSpec(BaseModel):
    machine: ModalityMachineSpec
    dicom_enabler: UUID4
    assignment_status: AssignmentStatus | None = None


class DicomDeviceMetadataReadSpec(BaseModel):
    machine: ModalityMachineSpec | None = None
    dicom_enabler: UUID4 | None = None
    assignment_status: AssignmentStatus | None = None
    last_synced_at: datetime | None = None


class DicomEnablerMetadataWriteSpec(BaseModel):
    ip: ipaddress.IPv4Address
    store_scp: DicomEndpointSpec
    modality_scp: DicomEndpointSpec
    assignment_status: AssignmentStatus | None = None


class DicomEnablerMetadataReadSpec(BaseModel):
    ip: ipaddress.IPv4Address | None = None
    store_scp: DicomEndpointSpec | None = None
    modality_scp: DicomEndpointSpec | None = None
    assignment_status: AssignmentStatus | None = None
    last_synced_at: datetime | None = None


class ModalityListQuerySpec(BaseModel):
    care_type: Literal["dicom-enabler", "dicom"] | None = None
    assignment_status: AssignmentStatus | None = None
    device_id: str | None = None
    device_name: str | None = None


class ModalityAssignmentStatusUpdateSpec(BaseModel):
    assignment_status: AssignmentStatus
