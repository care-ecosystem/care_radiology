from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('care_radiology', '0024_remove_accessionsequence_uniq_facility_modality_year_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='accessionsequence',
            options={'ordering': ['id']},
        ),
        migrations.AlterModelOptions(
            name='dicomstudy',
            options={'ordering': ['-created_date', '-id']},
        ),
        migrations.AlterModelOptions(
            name='imagingstudy',
            options={'ordering': ['-created_date', '-id']},
        ),
        migrations.AlterModelOptions(
            name='observationtemplate',
            options={'ordering': ['-created_date', '-id']},
        ),
        migrations.AlterModelOptions(
            name='observationtemplatedata',
            options={'ordering': ['id']},
        ),
        migrations.AlterModelOptions(
            name='radiologywebhooklogs',
            options={'ordering': ['-created_date', '-id']},
        ),
        migrations.AlterField(
            model_name='dicomstudy',
            name='dicom_study_uid',
            field=models.CharField(db_index=True, max_length=500),
        ),
    ]
