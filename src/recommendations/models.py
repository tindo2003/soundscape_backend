from django.db import models


# Create your models here.
class SeededRecs(models.Model):
    created = models.DateTimeField()
    source = models.TextField()
    target = models.TextField()
    support = models.DecimalField(max_digits=10, decimal_places=8)
    confidence = models.DecimalField(max_digits=10, decimal_places=8)
    type = models.CharField(max_length=8)

    class Meta:
        db_table = "seeded_recs"

    def __str__(self):
        return "[({} => {}) s = {}, c= {}]".format(
            self.source, self.target, self.support, self.confidence
        )


class CosineSimilarity(models.Model):
    created = models.DateField()
    source = models.TextField()
    target = models.TextField()
    similarity = models.DecimalField(max_digits=8, decimal_places=7)

    class Meta:
        db_table = "cosine_similarity"

    def __str__(self):
        return "[({} => {}) sim = {}]".format(self.source, self.target, self.similarity)
