from apps.numbering import patterns


def ticket_numbers(sequence):
    from .models import FaultReport

    numbers = []
    for value in FaultReport.objects.values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
