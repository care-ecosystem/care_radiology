import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("emr", "0079_resourcerequest_extensions"),
        ("facility", "0475_merge_20241223_2352"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("care_radiology", "0004_alter_scanprotocol_body_part_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ObservationTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)),
                ("created_date", models.DateTimeField(auto_now_add=True, null=True, blank=True, db_index=True)),
                ("modified_date", models.DateTimeField(auto_now=True, null=True, blank=True, db_index=True)),
                ("deleted", models.BooleanField(default=False, db_index=True)),
                ("history", models.JSONField(default=dict)),
                ("meta", models.JSONField(default=dict)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, null=True)),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="radiology_observation_templates",
                        to="facility.facility",
                    ),
                ),
                (
                    "observation_definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="radiology_templates",
                        to="emr.observationdefinition",
                    ),
                ),
                (
                    "activity_definition",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="radiology_observation_templates",
                        to="emr.activitydefinition",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_updated_by",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ObservationTemplateData",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=255)),
                ("value", models.TextField()),
                ("description", models.TextField(blank=True, null=True)),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="data",
                        to="care_radiology.observationtemplate",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="observationtemplate",
            index=models.Index(
                fields=["observation_definition", "activity_definition"],
                name="care_radiol_obs_def_act_def_idx",
            ),
        ),
    ]
