from django.db import models


class AccessionSequence(models.Model):
    """Per-(facility, modality_code, year) counter backing accession number generation."""

    facility = models.ForeignKey(
        "facility.Facility",
        on_delete=models.CASCADE,
        related_name="radiology_accession_sequences",
    )
    modality_code = models.CharField(max_length=100, blank=True)
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "modality_code", "year"],
                name="uniq_facility_modality_year",
            ),
        ]
