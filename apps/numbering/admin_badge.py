from .checks import check
from .models import NumberSequence


def problems(request):
    """Number of sequences whose counter does not match the documents (shown in the admin menu)."""
    if not request.user.has_perm("numbering.view_numbersequence"):
        return ""
    count = sum(1 for seq in NumberSequence.objects.all() if check(seq).has_problem)
    return str(count) if count else ""
