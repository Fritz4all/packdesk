"""The relation diagram: where each item goes on the page. Drawn as SVG by templates/admin/cmdb/_diagram.html.

Rows top to bottom follow the arrows: an item stands above what it needs, so what everything leans on is at the bottom.
In a row, items move towards the items they are connected to, which keeps the lines short. Circles in the data are
allowed: an arrow that closes one simply points upwards.
"""

from collections import defaultdict

from django.urls import reverse

from .models import ConfigurationItem, Relation

NODE_WIDTH, NODE_HEIGHT = 190, 58
GAP_X, GAP_Y = 36, 74
MARGIN = 12
SWEEPS = 4
MAX_ITEMS = 300
NAME_LENGTH = 26


def _levels(ids, needs):
    """The row of each item: the longest way down from an item that nothing needs."""
    needed_by = defaultdict(set)
    for source, targets in needs.items():
        for target in targets:
            needed_by[target].add(source)
    level = {}

    def visit(pk, on_path):
        if pk in level:
            return level[pk]
        best = 0
        for parent in needed_by[pk]:
            if parent not in on_path:
                best = max(best, visit(parent, on_path | {pk}) + 1)
        level[pk] = best
        return best

    for pk in ids:
        visit(pk, frozenset())
    return level


def _order(rows, needs):
    """Sort each row by the average position of its neighbours, a few times up and down."""
    neighbours = defaultdict(set)
    for source, targets in needs.items():
        for target in targets:
            neighbours[source].add(target)
            neighbours[target].add(source)
    position = {pk: i for row in rows for i, pk in enumerate(row)}
    for sweep in range(SWEEPS):
        for row in (rows if sweep % 2 == 0 else reversed(rows)):
            def centre(pk):
                around = [position[n] for n in neighbours[pk] if n in position]
                return sum(around) / len(around) if around else position[pk]
            row.sort(key=centre)
            for i, pk in enumerate(row):
                position[pk] = i
    return rows


def _pass_row(x, row, place):
    """Where a line at `x` crosses a row it does not stop at: at `x`, or else in the nearest gap beside a box."""
    for pk in row:
        left = place[pk][0]
        if left - GAP_X / 4 < x < left + NODE_WIDTH + GAP_X / 4:
            before, after = left - GAP_X / 2, left + NODE_WIDTH + GAP_X / 2
            return before if x - before < after - x else after
    return x


def _curve(x1, y1, x2, y2):
    bend = (y2 - y1) / 2
    return f"C{x1:g} {y1 + bend:g} {x2:g} {y2 - bend:g} {x2:g} {y2:g}"


def _route(source, target, rows, source_level, target_level, place):
    """(path, label x, label y) of an arrow. One that skips rows goes around the boxes in them."""
    x1, x2 = source[0] + NODE_WIDTH / 2, target[0] + NODE_WIDTH / 2
    if target_level <= source_level:  # same row or upwards, in a circle: from the top of the box to the bottom of the other
        y1, y2 = source[1], target[1] + NODE_HEIGHT + 3
        bend = max(abs(y2 - y1) / 2, 30)
        direction = 1 if y2 > y1 else -1
        path = f"M{x1:g} {y1:g} C{x1:g} {y1 + direction * bend:g} {x2:g} {y2 - direction * bend:g} {x2:g} {y2:g}"
        return path, (x1 + x2) / 2, (y1 + y2) / 2
    y1, y2 = source[1] + NODE_HEIGHT, target[1] - 3
    parts, x, y = [f"M{x1:g} {y1:g}"], x1, y1
    label = None
    between = range(source_level + 1, target_level)
    for number, r in enumerate(between, start=1):
        straight = x1 + (x2 - x1) * number / (len(between) + 1)
        through = _pass_row(straight, rows[r], place)
        top = MARGIN + r * (NODE_HEIGHT + GAP_Y)
        parts.append(_curve(x, y, through, top))
        label = label or ((x + through) / 2, (y + top) / 2)
        parts.append(f"L{through:g} {top + NODE_HEIGHT:g}")
        x, y = through, top + NODE_HEIGHT
    parts.append(_curve(x, y, x2, y2))
    label_x, label_y = label or ((x + x2) / 2, (y + y2) / 2)
    return " ".join(parts), label_x, label_y


def build(items, relations, focus=None):
    """{width, height, nodes, edges} for connected items. `focus` is highlighted, with what it affects when it fails."""
    by_pk = {item.pk: item for item in items}
    needs = defaultdict(set)
    labels = defaultdict(list)
    for relation in relations:
        if relation.source_id in by_pk and relation.target_id in by_pk:
            needs[relation.source_id].add(relation.target_id)
            labels[relation.source_id, relation.target_id].append(str(relation.kind))
    level = _levels(list(by_pk), needs)
    rows = [[] for _i in range(max(level.values(), default=-1) + 1)]
    for pk in sorted(by_pk, key=lambda pk: by_pk[pk].name.lower()):
        rows[level[pk]].append(pk)
    rows = _order(rows, needs)

    widest = max((len(row) for row in rows), default=0)
    width = widest * NODE_WIDTH + max(widest - 1, 0) * GAP_X + 2 * GAP_X  # room for a line beside the outer boxes
    height = len(rows) * NODE_HEIGHT + max(len(rows) - 1, 0) * GAP_Y + 2 * MARGIN
    affected = {item.pk for item in focus.affected_items()} if focus is not None else set()
    place, nodes = {}, []
    for r, row in enumerate(rows):
        row_width = len(row) * NODE_WIDTH + max(len(row) - 1, 0) * GAP_X
        left = (width - row_width) / 2
        for i, pk in enumerate(row):
            x, y = left + i * (NODE_WIDTH + GAP_X), MARGIN + r * (NODE_HEIGHT + GAP_Y)
            place[pk] = (x, y)
            item = by_pk[pk]
            nodes.append({
                "x": x, "y": y, "width": NODE_WIDTH, "height": NODE_HEIGHT, "number": item.number, "full_name": item.name,
                "name": item.name if len(item.name) <= NAME_LENGTH else item.name[:NAME_LENGTH - 1] + "…",
                "type": str(item.item_type), "status": str(item.status), "colour": item.status.colour,
                "url": reverse("admin:cmdb_configurationitem_change", args=[pk]),
                "state": "focus" if focus is not None and pk == focus.pk else ("affected" if pk in affected else ""),
            })
    edges = []
    for (source, target), kinds in labels.items():
        path, label_x, label_y = _route(place[source], place[target], rows, level[source], level[target], place)
        edges.append({"path": path, "label": ", ".join(sorted(kinds)), "label_x": label_x, "label_y": label_y})
    return {"width": width, "height": height, "nodes": nodes, "edges": edges}


def for_customer(customer):
    """(diagram, items without relations, more) for all items of a customer; `more` is how many did not fit."""
    query = (ConfigurationItem.objects.filter(customer=customer)
             .select_related("item_type", "status").order_by("name"))
    relations = list(Relation.objects.filter(source__customer=customer).select_related("kind"))
    linked = {r.source_id for r in relations} | {r.target_id for r in relations}
    items = list(query.filter(pk__in=linked)[:MAX_ITEMS])
    return build(items, relations), list(query.exclude(pk__in=linked)[:MAX_ITEMS]), max(len(linked) - MAX_ITEMS, 0)


def for_item(item):
    """The diagram of everything an item is connected to, directly or through others."""
    seen, current = {item.pk}, [item.pk]
    relations = {}
    while current and len(seen) < MAX_ITEMS:
        rows = Relation.objects.filter(source_id__in=current) | Relation.objects.filter(target_id__in=current)
        current = []
        for relation in rows.select_related("kind"):
            relations[relation.pk] = relation
            for pk in (relation.source_id, relation.target_id):
                if pk not in seen:
                    seen.add(pk)
                    current.append(pk)
    if not relations:
        return None
    items = list(ConfigurationItem.objects.filter(pk__in=seen).select_related("item_type", "status"))
    return build(items, relations.values(), focus=item)
