import time

from rest_framework import status
from rest_framework.response import Response

from care_radiology.services.dicom_service import DicomUploadError, StudyLinkConflictError, upload_dicom_file
from care_radiology.settings import plugin_settings
from care_radiology.utils import server_timing
from care_radiology.utils.server_timing import timed


class ServerTimingMixin:
    """
    Adds a `Server-Timing` header with the request's step timings when CARE_RADIOLOGY_SERVER_TIMING_ENABLED is on.
    `drf-initial` is DRF's authentication, permission and throttle checks. The commit of the request's transaction
    (ATOMIC_REQUESTS) runs after the view returns, so it is not part of `total`.
    """

    def dispatch(self, request, *args, **kwargs):
        if not plugin_settings.CARE_RADIOLOGY_SERVER_TIMING_ENABLED:
            return super().dispatch(request, *args, **kwargs)
        started = time.perf_counter()
        with server_timing.collect() as (entries, db):
            response = super().dispatch(request, *args, **kwargs)
            total_ms = (time.perf_counter() - started) * 1000
            response["Server-Timing"] = server_timing.header_value(entries, db, total_ms)
        return response

    def initial(self, request, *args, **kwargs):
        with timed("drf-initial", "authentication + permissions"):
            return super().initial(request, *args, **kwargs)


class DicomUploadMixin:
    def handle_dicom_upload(self, imaging_study, dicom, user=None):
        try:
            with timed("upload-service", "upload_dicom_file, sum of the steps below"):
                result = upload_dicom_file(imaging_study, dicom, user=user)
        except DicomUploadError as e:
            return Response(
                data={"errors": [{"type": "dicom_upload_error", "msg": e.message, **e.extra}]},
                status=e.status_code,
            )
        except StudyLinkConflictError as e:
            # `uploaded` is set because the file is in PACS by this point: without it
            # the caller reads a 409 here as a rejected upload and retries, which the
            # duplicate check then turns into a second, unrelated-looking 409.
            return Response(
                data={
                    "errors": [
                        {"type": "study_link_conflict", "msg": e.message, "uploaded": True, "study_uid": e.study_uid}
                    ]
                },
                status=status.HTTP_409_CONFLICT,
            )

        data = {"message": "DICOM files uploaded to DCM4CHE successfully", **result}
        if imaging_study.service_request_id is not None:
            data["service_request_id"] = str(imaging_study.service_request.external_id)
        return Response(data=data, status=status.HTTP_201_CREATED)
