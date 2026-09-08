import logging

logger = logging.getLogger(__name__)


def get_patient_uhid(patient):
    from care.emr.models.patient import PatientIdentifierConfigCache

    identifiers = patient.instance_identifiers
    if not isinstance(identifiers, list):
        return None

    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue

        config_external_id = identifier.get("config")
        if not config_external_id:
            continue

        try:
            config = PatientIdentifierConfigCache.get_config(config_external_id)
        except Exception:
            logger.warning(
                "Failed to resolve patient identifier config %s",
                config_external_id,
                exc_info=True,
            )
            continue

        nested = config.get("config") if isinstance(config, dict) else None
        if not isinstance(nested, dict):
            continue

        display = nested.get("display")

        if isinstance(display, str) and display.lower() == "uhid":
            return identifier.get("value")

    return None
