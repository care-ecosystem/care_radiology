import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('care_radiology', '0017_backfill_radiologyservicerequest_encounter'),
    ]

    operations = [
        migrations.AlterField(
            model_name='radiologyservicerequest',
            name='encounter',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='radiology_service_requests', to='emr.encounter'),
        ),
    ]
