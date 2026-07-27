from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("care_radiology", "0005_observationtemplate"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="observationtemplate",
            constraint=models.UniqueConstraint(
                fields=["facility", "title"],
                name="unique_facility_observation_template_title",
            ),
        ),
    ]
