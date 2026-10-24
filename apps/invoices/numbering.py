from apps.numbering import patterns


def invoice_numbers(sequence):
    """Numbers of invoices made in PackDesk and imported from the archive."""
    from .models import Invoice

    numbers = []
    for value in Invoice.objects.values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
