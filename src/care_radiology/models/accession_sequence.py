from django.db import models


class AccessionSequence(models.Model):
    """Per-(facility, resourcecategory, year) counter backing accession number generation."""

    facility = models.ForeignKey(
        "facility.Facility",
        on_delete=models.CASCADE,
        related_name="radiology_accession_sequences",
    )
    resourcecategory = models.ForeignKey(
        "emr.ResourceCategory",
        on_delete=models.PROTECT,
        related_name="radiology_accession_sequences",
    )
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "resourcecategory", "year"],
                name="uniq_facility_resource_category_year",
            ),
        ]
