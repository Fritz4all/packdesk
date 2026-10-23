from apps.numbering import patterns


def licence_numbers(sequence):
    """Counter values of existing licence numbers (only those of the current pattern)."""
    from .models import Licence

    numbers = []
    for value in Licence.objects.values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
