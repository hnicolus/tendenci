# Generated by Django 2.2.15 on 2020-08-10 17:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corporate_memberships', '0019_auto_20200810_1711'),
    ]

    operations = [
        migrations.AddField(
            model_name='corpmembership',
            name='donation_amount',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=15),
        ),
    ]