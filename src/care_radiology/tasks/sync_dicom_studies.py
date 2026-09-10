import logging

import psycopg
from care.emr.models.service_request import ServiceRequest
from celery import shared_task

from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.radiology_service_request import RadiologyServiceRequest
from care_radiology.utils.dicom import fetch_study

logger = logging.getLogger(__name__)


@shared_task
def sync_dicom_studies():
    conn = None
    try:
        conn = psycopg.connect("postgresql://postgres:postgres@db:5432/dicom")  # Move to ENV
        with conn.cursor() as cur:
            cur.execute("SELECT pk, study_iuid FROM study WHERE care_processed_status = 'pending'")
            rows = cur.fetchall()
            for row in rows:
                study = fetch_study(row[1])
                accession_number = study["study_accession"][0] if len(study["study_accession"]) > 0 else None
                if accession_number and len(accession_number.strip()) == 16:
                    sr_lookup_str = accession_number[:4] + "-" + accession_number[4:]
                    sr = ServiceRequest.objects.get(external_id__endswith=sr_lookup_str)
                    (ds, ds_created) = DicomStudy.objects.get_or_create(
                        dicom_study_uid=study["study_uid"], patient=sr.patient, defaults={}
                    )
                    if sr and ds:
                        RadiologyServiceRequest.objects.update_or_create(
                            service_request=sr, dicom_study=ds, defaults={"raw_data": {}}
                        )
                        cur.execute(
                            "UPDATE study SET care_processed_status = %s where study_iuid = %s",
                            ["success", study["study_uid"]],
                        )
        conn.commit()
    except psycopg.Error:
        logger.exception("Database error during DICOM study sync")
        if conn:
            conn.rollback()
    except ServiceRequest.DoesNotExist as e:
        logger.warning("Service request not found during DICOM study sync: %s", e)
        if conn:
            conn.rollback()
    except Exception:
        logger.exception("Unexpected error during DICOM study sync")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
