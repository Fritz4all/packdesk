"""Step 2 of 3 of moving payment methods to orders: spare parts orders point to the model in orders, and the
model is no longer part of spare parts. Nothing changes in the database."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("parts", "0004_delivery_taken_back"), ("orders", "0003_payment_method_moved")]
    operations = [
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.AlterField(
                model_name="partorder", name="payment_method",
                field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                        to="orders.paymentmethod", verbose_name="payment method"),
            ),
            migrations.DeleteModel(name="PaymentMethod"),
        ]),
    ]
