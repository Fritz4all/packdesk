from apps.numbering import patterns


def order_numbers(sequence):
    from .models import Order

    numbers = []
    for value in Order.objects.values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
