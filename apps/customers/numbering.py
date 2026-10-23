from apps.numbering import patterns


def customer_numbers(sequence):
    """Counter values of existing customer numbers, read back through the sequence pattern."""
    from .models import Customer

    numbers = []
    for value in Customer.objects.exclude(number="").values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
