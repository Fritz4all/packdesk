from apps.numbering import patterns


def request_numbers(sequence):
    from .models import PartRequest

    numbers = []
    for value in PartRequest.objects.values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
