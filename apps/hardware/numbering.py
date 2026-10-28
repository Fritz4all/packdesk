from apps.numbering import patterns


def device_numbers(sequence):
    from .models import Device

    numbers = []
    for value in Device.objects.values_list("number", flat=True):
        n = patterns.number_from(sequence.pattern, value)
        if n is not None:
            numbers.append(n)
    return numbers
