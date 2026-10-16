from django.db import migrations
from django.db.models import OuterRef, Subquery


def backfill_encounter(apps, schema_editor):
    RadiologyServiceRequest = apps.get_model('care_radiology', 'RadiologyServiceRequest')
    ServiceRequest = apps.get_model('emr', 'ServiceRequest')

    RadiologyServiceRequest.objects.filter(
        encounter__isnull=True, service_request__isnull=False
    ).update(
        encounter_id=Subquery(
            ServiceRequest.objects.filter(id=OuterRef('service_request_id')).values('encounter_id')[:1]
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ('care_radiology', '0016_remove_radiologyservicerequest_created_by_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_encounter, migrations.RunPython.noop),
    ]
