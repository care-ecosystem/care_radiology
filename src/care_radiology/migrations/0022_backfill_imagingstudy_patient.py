from django.db import migrations
from django.db.models import OuterRef, Subquery


def backfill_patient(apps, schema_editor):
    ImagingStudy = apps.get_model('care_radiology', 'ImagingStudy')
    DicomStudy = apps.get_model('care_radiology', 'DicomStudy')
    Encounter = apps.get_model('emr', 'Encounter')

    ImagingStudy.objects.filter(patient__isnull=True).update(
        patient_id=Subquery(Encounter.objects.filter(id=OuterRef('encounter_id')).values('patient_id')[:1])
    )

    # DicomStudy.imaging_study becomes non-null and DicomStudy.patient is dropped next, so a study
    # with no imaging study would be left with neither. These are unreachable through the API
    # already; their files stay in the PACS.
    DicomStudy.objects.filter(imaging_study__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('care_radiology', '0021_imagingstudy_patient'),
    ]

    operations = [
        migrations.RunPython(backfill_patient, migrations.RunPython.noop),
    ]
