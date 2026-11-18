from rest_framework import status
from rest_framework.response import Response

from care_radiology.services.dicom_service import DicomUploadError, StudyLinkConflictError, upload_dicom_file


class DicomUploadMixin:
    def handle_dicom_upload(self, imaging_study, dcm_file, user=None):
        try:
            result = upload_dicom_file(imaging_study, dcm_file, user=user)
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
