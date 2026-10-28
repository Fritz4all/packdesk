"""Payment methods move from spare parts to orders, so spare parts and hardware share them.

Step 1 of 3: Django learns that the model now lives here; the table stays as it is (parts_paymentmethod)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_defaults"), ("parts", "0004_delivery_taken_back")]
    operations = [
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.CreateModel(
                name="PaymentMethod",
                fields=[
                    ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                    ("code", models.SlugField(max_length=32, unique=True, verbose_name="code")),
                    ("name", models.CharField(max_length=100, verbose_name="name")),
                    ("name_nl", models.CharField(max_length=100, null=True, verbose_name="name")),
                    ("name_en", models.CharField(max_length=100, null=True, verbose_name="name")),
                    ("name_de", models.CharField(max_length=100, null=True, verbose_name="name")),
                    ("on_account", models.BooleanField(default=False, help_text="Delivered before payment. Large orders wait for approval (see the settings). Without this, an order waits until it is paid.", verbose_name="on account")),
                    ("extra_costs", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="extra costs (€)")),
                    ("is_active", models.BooleanField(default=True, verbose_name="active")),
                    ("position", models.PositiveSmallIntegerField(default=0, verbose_name="order")),
                ],
                options={"verbose_name": "payment method", "verbose_name_plural": "payment methods",
                         "ordering": ["position", "name"], "db_table": "parts_paymentmethod"},
            ),
        ]),
    ]
