from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("loanpulse_app", "0003_loanapplication_applicant_user")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="staff_registration_status",
            field=models.CharField(default="NONE", max_length=20),
        ),
    ]
