from apps.numbering import patterns


def item_numbers(sequence):
    from .models import ConfigurationItem

    numbers = []
    for value in ConfigurationItem.objects.values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
